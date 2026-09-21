# NetWatch — Task Status

Stack: Python, PySide6 (Qt), psutil, uv (`uv run NetWatch`)

## Done
- [x] Per-app connection monitoring (psutil-based, 2s polling)
- [x] Live process list with per-app connection count + sparkline history
- [x] Flagged / unknown-destination detection
- [x] BLOCK action — fully terminates the connection (real firewall-level block, not just UI)
- [x] Connections-over-time graph per selected app
- [x] Summary counters: active connections, active processes, blocked apps, unknown destinations

## In Progress (this pass)
- [x] Full dark-mode UI pass (QSS theme rewrite)
- [x] Replace stock checkboxes with iOS-style slider/toggle switches
- [x] Reduce visual density — spacing/padding pass across process list + detail pane
- [ ] Custom frameless title bar with proper minimize / maximize / close icons

## Pending / Not Started
- [ ] Persistent connection history (SQLite) — currently live/in-memory only, resets on restart
- [ ] Blocked-app history log (which apps were blocked, when, why)
- [ ] Reverse-DNS / domain resolution for `unresolved` remote IPs
- [ ] Decide on capture architecture upgrade path: stay on psutil polling vs. move to event-driven capture (pydivert/WinDivert) for instant (non-2s-delayed) connection detection
- [ ] Packaging/distribution (PyInstaller/Nuitka single-exe build)

## Open Questions (not yet decided)
- GUI framework confirmation: assumed current UI is a prototype; standardizing on PySide6 going forward
- Whether "unresolved" IPs should stay flagged red intentionally (no-PTR = suspicious signal) once DNS resolution is added
