"""RSM feature: STAGE 1/2 data pipeline (front-end agnostic).

Pure load/build/regrid helpers extracted verbatim from ``create_server``. They
take the trame ``state`` (and, where they log, a ``set_status`` callback) as
explicit arguments instead of closing over ``create_server`` locals -- so the
feature owns its reconstruction pipeline and tomography can add a parallel one.
No VTK / rendering here (proven render-free by AST analysis).
"""

import yaml
from pathlib import Path

from voxel.services.backend import RSMDataLoader_ISR, RSMDataloader_CMS, RSMBuilder
from voxel.services.parsing import (
    _float,
    _ensure_path,
    _scan_numbers_in_dir_CMS,
    _scan_numbers_in_dir_ISR,
    _parse_scan_list,
    _parse_ub_matrix,
    _format_ub_matrix,
)


def _selected_scans_from_state(state, tiff_dir):
    """Resolve the Data-tab scan-range text to an explicit scan list.

    Parses the scan ids from the TIFF filenames and keeps those matching
    the user's scan-range string (e.g. "17-20, 30"). An empty string loads
    everything. Raises ValueError on malformed input.

    CMS filenames have a single scan number per frame, so the parsed
    scan ids come straight from ``_scan_numbers_in_dir_CMS``. ISR filenames
    have a (scan_number, data_number) pair; the scan-range text selects
    whole scan numbers and every data frame within a selected scan is
    loaded, so only the unique scan numbers are matched here. In both cases
    the returned list is the scan-number list the loaders'
    ``selected_scans`` argument expects.
    """
    loader_mode = _ensure_path(state.loader_mode).upper() or "CMS"
    if loader_mode == "ISR":
        scans = sorted({scan for scan, _data in _scan_numbers_in_dir_ISR(tiff_dir)})
    else:
        scans = _scan_numbers_in_dir_CMS(tiff_dir)
    if not scans:
        return None
    requested = _parse_scan_list(getattr(state, "scan_range", ""))
    if not requested:
        return None
    available = set(scans)
    selected = sorted(s for s in requested if s in available)
    return selected or None

def _load_experiment(state, loader_mode):
    setup_path = Path(_ensure_path(state.setup_path)).expanduser()
    tiff_dir = Path(_ensure_path(state.tiff_dir)).expanduser()
    selected_scans = _selected_scans_from_state(state, str(tiff_dir))
    if loader_mode == "ISR":
        spec_path = Path(_ensure_path(state.spec_path)).expanduser()
        loader = RSMDataLoader_ISR(
            str(spec_path),
            str(setup_path),
            str(tiff_dir),
            use_dask=False,
            selected_scans=selected_scans,
            process_hklscan_only=bool(getattr(state, "only_hkl", False)),
        )
        setup, ub, df = loader.load()
    else:
        loader = RSMDataloader_CMS(
            str(setup_path),
            str(tiff_dir),
            angle_step=_float(state.cms_angle_step, 1.0),
            selected_scans=selected_scans,
        )
        setup, ub, df = loader.load()
    frames = None
    if df is not None and "intensity" in getattr(df, "columns", []):
        frames = list(df["intensity"])
    return setup, ub, df, frames

def _populate_setup_fields(state, setup, frames):
    """Reflect a loaded ExperimentSetup into the Data-tab fields."""
    if setup is not None:
        state.exp_distance = float(getattr(setup, "distance", 0.0) or 0.0)
        state.exp_pitch = float(getattr(setup, "pitch", 0.0) or 0.0)
        state.exp_det_h = int(getattr(setup, "ypixels", 0) or 0)
        state.exp_det_w = int(getattr(setup, "xpixels", 0) or 0)
        state.exp_bc_h = int(getattr(setup, "ycenter", 0) or 0)
        state.exp_bc_w = int(getattr(setup, "xcenter", 0) or 0)
        state.exp_energy = float(getattr(setup, "energy", 0.0) or 0.0)
        state.exp_wavelength = float(getattr(setup, "wavelength", 0.0) or 0.0)
    # Detector dimensions from the actual frames take precedence.
    if frames:
        first = frames[0]
        if hasattr(first, "shape") and len(first.shape) >= 2:
            h, w = int(first.shape[-2]), int(first.shape[-1])
            state.exp_det_h = h
            state.exp_det_w = w

def _read_profile_section(state, loader_mode):
    """Return the YAML profile dict matching the chosen ``loader_mode``.

    The bundled loaders always read ExperimentSetup from the YAML's
    ``active_profile`` section, so the Data-tab ISR/CMS choice would
    otherwise be ignored. We read the requested profile directly here
    (web-app only) so the selected beamline's parameters drive the UI and
    the build instead of whatever happens to be the active profile on disk.
    """
    path = Path(_ensure_path(state.setup_path)).expanduser()
    if not path.is_file():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            doc = yaml.safe_load(handle) or {}
    except Exception:
        return None
    profiles = doc.get("profiles")
    if not isinstance(profiles, dict):
        return None
    target = _ensure_path(loader_mode).upper()
    for name, section in profiles.items():
        if str(name).upper() == target and isinstance(section, dict):
            return section
    return None

def _populate_from_profile(state, loader_mode):
    """Fill the Data/Build/View fields from the chosen beamline profile.

    Runs immediately when the loader mode changes (and at startup) so the
    experimental setup values and related parameters reflect the ISR/CMS
    choice before any TIFF directory is picked or data is loaded.
    """
    section = _read_profile_section(state, loader_mode)
    if section is None:
        return

    setup = section.get("ExperimentSetup")
    if isinstance(setup, dict):
        state.exp_distance = _float(setup.get("distance"), state.exp_distance)
        state.exp_pitch = _float(setup.get("pitch"), state.exp_pitch)
        state.exp_det_h = int(_float(setup.get("ypixels"), state.exp_det_h))
        state.exp_det_w = int(_float(setup.get("xpixels"), state.exp_det_w))
        state.exp_bc_h = int(_float(setup.get("ycenter"), state.exp_bc_h))
        state.exp_bc_w = int(_float(setup.get("xcenter"), state.exp_bc_w))
        energy = _float(setup.get("energy"), 0.0)
        if energy > 0:
            # Setting energy keeps wavelength in sync via _on_energy_change.
            state.exp_energy = energy
        else:
            wavelength = _float(setup.get("wavelength"), 0.0)
            if wavelength > 0:
                state.exp_wavelength = wavelength

    crystal = section.get("Crystal")
    if isinstance(crystal, dict) and crystal.get("ub") is not None:
        try:
            ub_arr = _parse_ub_matrix(str(crystal["ub"]))
        except ValueError:
            ub_arr = None
        if ub_arr is not None:
            state.ub_matrix = _format_ub_matrix(ub_arr)

    build = section.get("build")
    if isinstance(build, dict):
        if build.get("sample_axes") is not None:
            state.sample_axes = str(build["sample_axes"])
        if build.get("detector_axes") is not None:
            state.detector_axes = str(build["detector_axes"])
        if build.get("ub_includes_2pi") is not None:
            state.ub_includes_2pi = bool(build["ub_includes_2pi"])
        if build.get("center_is_one_based") is not None:
            state.one_based_center = bool(build["center_is_one_based"])

    regrid = section.get("regrid")
    if isinstance(regrid, dict):
        if regrid.get("space") is not None:
            state.space = str(regrid["space"])
        if regrid.get("grid_shape") is not None:
            state.grid_shape = str(regrid["grid_shape"])
        if regrid.get("normalize") is not None:
            state.normalize = str(regrid["normalize"])
        if regrid.get("fuzzy") is not None:
            state.fuzzy_gridder = bool(regrid["fuzzy"])
        if regrid.get("fuzzy_width") is not None:
            state.width_fuzzy = _float(regrid.get("fuzzy_width"), state.width_fuzzy)

    data = section.get("data")
    if isinstance(data, dict) and data.get("cms_angle_step") is not None:
        state.cms_angle_step = _float(data.get("cms_angle_step"), state.cms_angle_step)

    view = section.get("view")
    if isinstance(view, dict):
        if view.get("log_view") is not None:
            state.log_view = bool(view["log_view"])
        if view.get("cmap") is not None:
            state.colormap = str(view["cmap"])
        if view.get("rendering") is not None:
            state.rendering = str(view["rendering"])
        if view.get("contrast_lo") is not None:
            state.contrast_lo = _float(view.get("contrast_lo"), state.contrast_lo)
        if view.get("contrast_hi") is not None:
            state.contrast_hi = _float(view.get("contrast_hi"), state.contrast_hi)

def _override_setup_with_profile(state, setup, loader_mode):
    """Force a loaded setup's geometry to match the chosen profile.

    The bundled loaders read ExperimentSetup from the YAML ``active_profile``
    section, which need not match the Data-tab ISR/CMS choice. We overwrite
    the geometry here so the loaded ``setup`` (and everything built from it:
    crop adjustments, the displayed fields, and the regrid) reflects the
    selected beamline rather than the active profile on disk.
    """
    if setup is None:
        return
    section = _read_profile_section(state, loader_mode)
    if section is None:
        return
    exp = section.get("ExperimentSetup")
    if not isinstance(exp, dict):
        return
    try:
        distance = _float(exp.get("distance"), 0.0)
        if distance > 0:
            setup.distance = distance
        pitch = _float(exp.get("pitch"), 0.0)
        if pitch > 0:
            setup.pitch = pitch
        ypixels = int(_float(exp.get("ypixels"), 0))
        if ypixels > 0:
            setup.ypixels = ypixels
        xpixels = int(_float(exp.get("xpixels"), 0))
        if xpixels > 0:
            setup.xpixels = xpixels
        setup.ycenter = int(_float(exp.get("ycenter"), setup.ycenter))
        setup.xcenter = int(_float(exp.get("xcenter"), setup.xcenter))
        energy = _float(exp.get("energy"), 0.0)
        if energy > 0:
            setup.energy = energy
            setup.energy_keV = energy
            setup.wavelength = 12.398419843320026 / energy
        else:
            wavelength = _float(exp.get("wavelength"), 0.0)
            if wavelength > 0:
                setup.wavelength = wavelength
                setup.energy_keV = 12.398419843320026 / wavelength
                setup.energy = setup.energy_keV
    except (TypeError, ValueError):
        pass

def _apply_setup_overrides(state, set_status, setup):
    """Push user-edited Data-tab values onto the setup before building."""
    if setup is None:
        return
    try:
        setup.distance = float(state.exp_distance) or setup.distance
        setup.pitch = float(state.exp_pitch) or setup.pitch
        setup.ypixels = int(state.exp_det_h) or setup.ypixels
        setup.xpixels = int(state.exp_det_w) or setup.xpixels
        setup.ycenter = int(state.exp_bc_h)
        setup.xcenter = int(state.exp_bc_w)
        if float(state.exp_energy) > 0:
            setup.energy = float(state.exp_energy)
        if float(state.exp_wavelength) > 0:
            setup.wavelength = float(state.exp_wavelength)
    except (TypeError, ValueError) as exc:
        set_status(f"Setup override skipped: {exc}")

def _compute_builder(setup, ub, df, sample_axes, detector_axes,
                     ub_includes_2pi, center_is_one_based,
                     progress_callback=None):
    builder = RSMBuilder(
        setup,
        ub,
        df,
        sample_axes=sample_axes or None,
        detector_axes=detector_axes or None,
        ub_includes_2pi=ub_includes_2pi,
        center_is_one_based=center_is_one_based,
    )
    builder.compute_full(verbose=False, progress_callback=progress_callback)
    return builder

def _regrid_volume(state, builder, grid_shape, progress_callback=None):
    fuzzy = bool(getattr(state, "fuzzy_gridder", False))
    kwargs = dict(
        space=_ensure_path(state.space) or "q",
        grid_shape=grid_shape,
        normalize=_ensure_path(state.normalize) or "mean",
        fuzzy=fuzzy,
        # Accumulate the scattered points frame-by-frame (mirrors the napari
        # widget). Without streaming, regrid_xu ravels every frame's points
        # into one giant array, which can need gigabytes of RAM and fail to
        # allocate for large scans.
        stream=True,
    )
    width = _float(getattr(state, "width_fuzzy", 0.0), 0.0)
    if fuzzy and width > 0:
        kwargs["width"] = width
    return builder.regrid_xu(progress_callback=progress_callback, **kwargs)

