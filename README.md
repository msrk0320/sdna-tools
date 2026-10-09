# SDNA Tools

Small Windows tools for 3D texturing work with Adobe Substance 3D Painter.

## Access

This repo is private. Only invite people using their @example.com email address (repo Settings > Collaborators > Add people > type the email). Remove people when they leave.

## Tools

| Tool | Description |
|------|-------------|
| `tools/spp-downgrader` | Drag-and-drop converter that rebuilds a Substance 3D Painter .spp/.uspp for an older Painter version. |

## Adding a tool

Put it in `tools/<name>/` with its own README.md and a setup script if it needs dependencies. Never commit client files (.spp, .uspp, .glb, .fbx), virtual environments, browser profiles or data folders — .gitignore blocks the common ones.
