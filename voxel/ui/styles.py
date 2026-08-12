"""Shared control-panel style helpers for the left accordion.

These are UI conventions shared by every feature that plugs tabs into the
left control panel (RSM today, tomography later). Keeping them here lets each
feature's ``ui`` module import the exact same accordion look without depending
on ``voxel/app/server.py``.
"""


def bar_style(key):
    """Reactive accordion-bar style binding for the tab named ``key``.

    Returns a trame style *binding* tuple (a Vue template literal) so the bar
    highlights live as ``open_tab`` changes.
    """
    return (
        "`display:flex; align-items:center; justify-content:space-between; "
        "cursor:pointer; padding:12px 14px; margin-bottom:6px; "
        f"background:${{open_tab === '{key}' ? '#d4e4fa' : '#f0f0f3'}}; "
        f"border:1px solid ${{open_tab === '{key}' ? '#a0b8d4' : '#dcdce0'}}; "
        "border-radius:6px; font-weight:600; user-select:none;`",
    )


# The panel only renders while its tab is open, so its outline is always the
# light-blue selected colour.
PANEL = (
    "border:1px solid #d4e4fa; border-top:none; border-radius:0 0 6px 6px; "
    "padding:14px; margin:-6px 0 10px 0; background:#fbfbfc;"
)
LBL = "display:block; margin-top:10px; font-size:0.85rem; color:#444;"
INP = "width:100%; margin-top:4px;"
BTN = "flex:1; padding:10px 8px; cursor:pointer;"
