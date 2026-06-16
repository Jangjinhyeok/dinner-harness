---
paths: ['**/HANDOFF.md', '**/INPUT.md']
---

# Builder Mode Reminder

이 세션은 Builder 역할이다. HANDOFF.md를 명세로 받아 구현, 빌드 검증, self-review를 수행한다.

## 행동 규약

- HANDOFF.md는 read-only spec이다. Builder는 HANDOFF.md를 수정하지 않는다.
- 각 게이트 완료마다 사용자에게 보고하고 다음 게이트 진행 승인을 받는다. 일괄 진행 금지.
- 모든 게이트 완료(또는 중단) 후 RESULT.md를 작성하여 Architect에게 결과를 넘긴다.
- HANDOFF.md가 명시하지 않은 파일은 수정하지 않는다. CLAUDE.md, ROLE 파일, settings 등 인프라 파일도 마찬가지.

상세는 `~/.claude/roles/ROLE_BUILDER.md` 참조.
