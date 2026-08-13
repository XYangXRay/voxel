"""RSM feature: binds the 3D reciprocal-space-map workflow to the shell contract.

This is the single object the shell talks to for the RSM front-end. Today it
delegates the UI hooks to :mod:`voxel.features.rsm.ui`; its scene/controller
hooks are inherited no-ops because RSM's VTK scene and ``@ctrl.set(...)`` step
handlers still live inline in ``voxel/app/server.py``. Stage 2 moves that code
into :meth:`setup_scene` / :meth:`register_controllers` here, at which point the
shell builds RSM purely through this contract (and tomography plugs in the same
way).
"""

from voxel.features.base import FeatureContext, VoxelFeature
from voxel.features.rsm import ui as rsm_ui


class RSMFeature(VoxelFeature):
    """The 3D RSM front-end, exposed through the shared feature contract."""

    key = "RSM"
    title = "RSM"

    def build_tabs(self, ctx: FeatureContext) -> None:
        rsm_ui.build_tabs(ctx)

    def build_layer_controls(self, ctx: FeatureContext) -> None:
        rsm_ui.build_layer_controls(ctx)

    # setup_scene() / register_controllers() intentionally inherit the base
    # no-ops for now: RSM's VTK scene and step handlers are still built inline
    # in create_server(). Stage 2 relocates them here.
