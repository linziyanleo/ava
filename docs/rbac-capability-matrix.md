# Console RBAC Capability Matrix

| Role | Read console state | Edit config/content | Submit direct tasks | Cancel background tasks | Admin users/system |
| --- | --- | --- | --- | --- | --- |
| `admin` | yes | yes | yes | yes | yes |
| `editor` | yes | yes | yes | yes | no |
| `viewer` | yes | no | no | no | no |
| `read_only` | yes | no | no | no | no |
| `mock_tester` | mock-safe read | no real runtime mutation | no | no | no |

Write endpoints must enforce the same boundary server-side. Frontend disabled states are only an affordance; they are not authorization.
