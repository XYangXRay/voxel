"""Feature contract: the interface every Voxel front-end feature implements.

The app *shell* (``voxel/app/server.py`` -> ``create_server``) owns everything
shared between features: the trame server, the reactive ``state``/``controller``,
the left control panel + accordion, the status area, the 3D view + the
``VtkRemoteView`` bridge, the layer list, and the file browser. A *feature*
(3D-RSM today, tomography next) fills in the parts specific to one workflow.

This module defines the boundary between the two so that:

* the shell can host any feature without knowing its internals, and
* every feature (RSM, tomography, ...) targets the same *stable* interface.

There are two pieces:

* :class:`FeatureContext` -- the handles the shell hands to a feature. A feature
  reads these; it never reaches back into ``create_server`` internals.
* :class:`VoxelFeature` -- the lifecycle a feature implements. The shell calls
  these hooks at fixed points while it builds the app.

Lifecycle, in the order the shell calls the hooks::

    1. setup_scene(ctx)           build VTK actors / renderer content
    2. register_controllers(ctx)  attach @ctrl.set(...) step handlers
    3. build_tabs(ctx)            emit the left-panel accordion tabs
    4. build_layer_controls(ctx)  emit the per-layer property editors

Every hook has a no-op default, so a feature overrides only what it needs and
new hooks can be added later without breaking existing features.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class FeatureContext:
    """Shared handles the shell passes to a feature.

    A feature receives one of these and uses it instead of reaching into the
    shell's ``create_server`` closure. New shared handles (e.g. scene objects
    once STAGE 1/2 move out of ``server.py``) are added here as fields so every
    feature keeps targeting the same object.

    Attributes:
        server:  the trame server (``trame.app.get_server`` result).
        state:   ``server.state`` -- the reactive UI state.
        ctrl:    ``server.controller`` -- where step handlers are registered.
        fb_open: opens the shared file-browser modal: ``fb_open(target, mode)``
                 where ``target`` is the state key to write and ``mode`` is
                 ``"file"`` or ``"dir"``.
    """

    server: Any
    state: Any
    ctrl: Any
    fb_open: Callable[..., Any]


class VoxelFeature:
    """Base class / contract for a Voxel feature.

    Subclass this, set :attr:`key` (must equal the ``current_view`` value used
    by the header view switcher) and :attr:`title`, and override the lifecycle
    hooks the feature needs. The shell drives the hooks in the documented order.
    """

    #: Identifier matching the ``current_view`` state value, e.g. ``"RSM"``.
    key: str = ""
    #: Human-readable label shown in the header view switcher.
    title: str = ""

    def setup_scene(self, ctx: FeatureContext) -> None:
        """Build this feature's VTK scene (actors, mappers, renderer content).

        Called once while the shell constructs the off-screen render window,
        before the UI is laid out. Default: no-op.
        """

    def register_controllers(self, ctx: FeatureContext) -> None:
        """Register this feature's ``@ctrl.set(...)`` step handlers.

        Called once after :meth:`setup_scene`. These are the button handlers the
        tabs bind to (load / build / view / export / ...). Default: no-op.
        """

    def build_tabs(self, ctx: FeatureContext) -> None:
        """Emit the left-panel accordion tabs for this feature.

        Called inside the shell's left-control-panel layout context; the widgets
        created here attach to that panel. Default: no-op.
        """

    def build_layer_controls(self, ctx: FeatureContext) -> None:
        """Emit the per-layer property editors for this feature.

        Called inside the shell's right-hand layer panel, above the shared layer
        list; the widgets created here attach to that panel. Default: no-op.
        """
