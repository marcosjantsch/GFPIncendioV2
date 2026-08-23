from __future__ import annotations

import streamlit.components.v1 as components


def render_idle_timeout(timeout_seconds: int = 180) -> None:
    components.html(
        f"""
        <script>
        (() => {{
          const host = window.parent;
          const timeoutMs = {int(timeout_seconds)} * 1000;
          const expiredUrl = "/app/static/session-expired.html";
          if (!host.__avantIdleState) {{
            const state = {{lastActivity: Date.now(), listeners: []}};
            const markActivity = () => {{ state.lastActivity = Date.now(); }};
            ["pointerdown", "pointermove", "keydown", "wheel", "touchstart", "scroll"].forEach((eventName) => {{
              host.addEventListener(eventName, markActivity, {{capture: true, passive: true}});
              state.listeners.push([eventName, markActivity]);
            }});
            state.intervalId = host.setInterval(() => {{
              if (Date.now() - state.lastActivity >= timeoutMs) {{
                host.clearInterval(state.intervalId);
                host.location.replace(expiredUrl);
              }}
            }}, 5000);
            host.__avantIdleState = state;
          }}
        }})();
        </script>
        """,
        height=0,
        width=0,
    )

