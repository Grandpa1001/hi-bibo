#!/bin/bash
# open-test-round.sh — Tworzy GitHub issues z TESTCASES.md dla danej wersji
#
# Użycie: ./scripts/open-test-round.sh V1.4
#         ./scripts/open-test-round.sh V1.4 --dry-run
#
# Wymaga: gh CLI zalogowany, label 'qa' na repo

set -euo pipefail

REPO="Grandpa1001/hi-bibo"
TESTCASES_FILE="$(dirname "$0")/../TESTCASES.md"
VERSION="${1:?Podaj wersję, np: ./open-test-round.sh V1.4}"
DRY_RUN="${2:-}"

# Upewnij się że label 'qa' istnieje
if ! gh label list -R "$REPO" | grep -q "^qa"; then
    echo "Tworzę label 'qa' na repo..."
    gh label create qa -R "$REPO" --color "fbca04" --description "Test case / QA scenario" 2>/dev/null || true
fi

# Twórz label per wersja jeśli nie istnieje
VERSION_LABEL="round:${VERSION}"
if ! gh label list -R "$REPO" | grep -q "^${VERSION_LABEL}"; then
    echo "Tworzę label '${VERSION_LABEL}' na repo..."
    gh label create "$VERSION_LABEL" -R "$REPO" --color "c5def5" --description "Test round ${VERSION}" 2>/dev/null || true
fi

# Parsuj TESTCASES.md — wyciągnij QA-XXX tytuły i body
count=0
current_id=""
current_title=""
current_body=""

flush_issue() {
    if [[ -n "$current_id" ]]; then
        full_title="[${current_id}] ${current_title} — ${VERSION}"
        full_body="**Wersja:** ${VERSION}
**Scenariusz:** ${current_id}

${current_body}

---
_Auto-generated from TESTCASES.md_"

        if [[ "$DRY_RUN" == "--dry-run" ]]; then
            echo "DRY-RUN: $full_title"
        else
            # Sprawdź czy już istnieje (unikaj duplikatów)
            existing=$(gh issue list -R "$REPO" --search "\"[${current_id}]\" \"${VERSION}\" in:title" --state open --json number --jq '.[0].number' 2>/dev/null || echo "")
            if [[ -n "$existing" && "$existing" != "null" ]]; then
                echo "SKIP: ${full_title} (already open as #${existing})"
            else
                gh issue create -R "$REPO" \
                    --title "$full_title" \
                    --body "$full_body" \
                    --label "qa,${VERSION_LABEL}"
                echo "CREATED: ${full_title}"
                count=$((count + 1))
                sleep 1  # rate limit
            fi
        fi
    fi
}

while IFS= read -r line; do
    if [[ "$line" =~ ^###[[:space:]]+(QA-[0-9]+):[[:space:]]+(.+)$ ]]; then
        flush_issue
        current_id="${BASH_REMATCH[1]}"
        current_title="${BASH_REMATCH[2]}"
        current_body=""
    elif [[ -n "$current_id" && "$line" != "---" ]]; then
        current_body+="${line}
"
    fi
done < "$TESTCASES_FILE"

# Flush last
flush_issue

if [[ "$DRY_RUN" != "--dry-run" ]]; then
    echo ""
    echo "✅ Utworzono ${count} issues dla rundy ${VERSION}"
else
    echo ""
    echo "DRY-RUN zakończony. Dodaj wersję bez --dry-run by utworzyć issues."
fi
