"""GraphQL documents sent to https://leetcode.com/graphql/.

IMPORTANT: this is LeetCode's *internal, undocumented* GraphQL API - the same one the
public profile page calls from the browser. It is not an official or stable API; the
field names below are the ones the profile page has used and may change without notice.
Run `python scripts/inspect_leetcode.py <username>` to re-check them against the live site.
"""
from __future__ import annotations

USER_PROFILE = """
query userPublicProfile($username: String!) {
  matchedUser(username: $username) {
    username
    profile { realName userAvatar ranking }
  }
}
"""

# Powers the "Skills" card (Advanced / Intermediate / Fundamental) on the profile page.
SKILL_STATS = """
query skillStats($username: String!) {
  matchedUser(username: $username) {
    tagProblemCounts {
      advanced { tagName tagSlug problemsSolved }
      intermediate { tagName tagSlug problemsSolved }
      fundamental { tagName tagSlug problemsSolved }
    }
  }
}
"""

# Powers the "Recent AC" list on the profile page. Takes only a limit: no offset, no cursor.
RECENT_AC_SUBMISSIONS = """
query recentAcSubmissions($username: String!, $limit: Int!) {
  recentAcSubmissionList(username: $username, limit: $limit) {
    id
    title
    titleSlug
    timestamp
  }
}
"""

# Recent submissions of every status (Accepted, Wrong Answer, ...). Also limit-only.
# Publicly it has exposed status and language but no submission id.
RECENT_SUBMISSIONS = """
query recentSubmissions($username: String!, $limit: Int) {
  recentSubmissionList(username: $username, limit: $limit) {
    title
    titleSlug
    timestamp
    statusDisplay
    lang
  }
}
"""


def build_difficulty_query(slugs: list[str]) -> tuple[str, dict[str, str], dict[str, str]]:
    """Build one aliased query that fetches the difficulty of several problems.

    Slugs are passed as variables (never interpolated) so they cannot alter the query.
    Returns (query, variables, alias -> slug).
    """
    params, fields, variables, alias_map = [], [], {}, {}
    for i, slug in enumerate(slugs):
        var, alias = f"s{i}", f"q{i}"
        params.append(f"${var}: String!")
        fields.append(f"  {alias}: question(titleSlug: ${var}) {{ titleSlug difficulty }}")
        variables[var] = slug
        alias_map[alias] = slug
    query = "query questionDifficulties(" + ", ".join(params) + ") {\n" + "\n".join(fields) + "\n}"
    return query, variables, alias_map
