"""
Transaction report parser.

The Pioneer League publishes transactions as plain text blocks:

    August 30                      <- date header, usually no year
    Idaho Falls Chukars            <- team header (the club making the move)
    - Signed Quintt Landis to their 2025 roster
    - Placed Christian Womble on Irrevocable waivers

This module turns those lines into structured rows and decides what each one
means for a player's signing status. It is pure Python with no network or
database access, so it can be unit tested against real report wording.

Other leagues (Frontier, American Association, Atlantic) use very similar
phrasing, so the same classifier is meant to be reused for them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MONTHS = {
    m: i for i, m in enumerate(
        ["january", "february", "march", "april", "may", "june", "july",
         "august", "september", "october", "november", "december"], start=1)
}
MONTH_ABBR = {k[:3]: v for k, v in MONTHS.items()}
MONTH_ABBR["sept"] = 9

# The 30 MLB clubs. A counterparty that matches one of these is an affiliated org.
MLB_CLUBS = [
    "Arizona Diamondbacks", "Athletics", "Oakland Athletics", "Atlanta Braves",
    "Baltimore Orioles", "Boston Red Sox", "Chicago Cubs", "Chicago White Sox",
    "Cincinnati Reds", "Cleveland Guardians", "Colorado Rockies", "Detroit Tigers",
    "Houston Astros", "Kansas City Royals", "Los Angeles Angels", "Los Angeles Dodgers",
    "Miami Marlins", "Milwaukee Brewers", "Minnesota Twins", "New York Mets",
    "New York Yankees", "Philadelphia Phillies", "Pittsburgh Pirates",
    "San Diego Padres", "San Francisco Giants", "Seattle Mariners",
    "St. Louis Cardinals", "Tampa Bay Rays", "Texas Rangers", "Toronto Blue Jays",
    "Washington Nationals",
]
_MLB_NICKNAMES = {c.split()[-1].lower() for c in MLB_CLUBS} | {"red sox", "white sox", "blue jays"}

# Position tags that sometimes precede a name: "RHP Michael Riley", "OF/RHP Chase Hanson".
_POS = r"(?:RHP|LHP|SP|RP|INF|IF|OF|UT|UTL|UTIL|C|1B|2B|3B|SS|LF|CF|RF|DH|P|MIF|CIF)"
POS_PREFIX = re.compile(rf"^(?:{_POS}(?:/{_POS})*)\s+")

# Verbs that start a transaction sentence. Used to strip a duplicated leading name
# such as "Elijah Young Traded Elijah Young to the RedPocket Mobiles ...".
_VERBS = r"(?:Traded|Tradeed|Trade|Acquired|Received|Signed|Re-signed|Resigned|Released|Claimed|Placed|Sold|Transferred|Reinstated|Activated|Moved|Exercised|Selected|Purchased)"

# Bullet characters seen in the wild: "-", "•", "–", "*".
BULLET = re.compile(r"^\s*[-•–—*·]\s*")

# Tails that end the counterparty part of a trade line.
_CP_TAIL = r"(?:\s+of the\s+[^,.]+?)?(?=\s+(?:for|in exchange|to complete|as)\b|[.,]|$)"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ParsedTxn:
    txn_date: date
    team: str                    # team header the line sat under
    raw_text: str                # the line as printed, bullet removed
    txn: str                     # one of the txn_type enum values
    player_name: Optional[str]   # cleaned full name, None if not found
    counterparty: Optional[str] = None   # other club named in the line
    counterparty_affiliated: Optional[bool] = None
    notes: list[str] = field(default_factory=list)

    @property
    def from_team(self) -> Optional[str]:
        """Club the player left, when the line implies one."""
        if self.txn in ("contract_sold", "released"):
            return self.team
        if self.txn == "traded":
            return self.counterparty if self._incoming else self.team
        return None

    @property
    def to_team(self) -> Optional[str]:
        """Club the player now belongs to, when the line implies one."""
        if self.txn == "signed":
            return self.team
        if self.txn == "contract_sold":
            return self.counterparty
        if self.txn == "traded":
            return self.team if self._incoming else self.counterparty
        return None

    @property
    def _incoming(self) -> bool:
        return bool(re.match(r"^(?:acquired|received|claimed)\b", self.raw_text, re.I))


# What each transaction type does to player_status.
#   None means "no change to status" (injury moves, reinstatements, etc.).
#   "team" means the status is signed_independent unless the destination club is affiliated.
STATUS_EFFECT = {
    "signed": "signed_independent",
    "contract_sold": "signed_affiliated",
    "released": "free_agent",
    "traded": "team",
    "drafted": "team",
    "retired": "retired",
    "suspended": None,
    "injury": None,
    "other": None,
}


def status_after(t: ParsedTxn) -> Optional[str]:
    """Signing status this transaction leaves the player in, or None for no change."""
    effect = STATUS_EFFECT.get(t.txn)
    if t.txn == "contract_sold" and t.counterparty_affiliated is False:
        # Sold to a non MLB club (Mexican League, Japan, another indy). Off the market, not affiliated.
        return "signed_independent"
    if effect == "team":
        return "signed_affiliated" if t.counterparty_affiliated and not t._incoming else "signed_independent"
    return effect


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def is_affiliated_club(name: Optional[str]) -> bool:
    """True when a club name refers to an MLB organization."""
    if not name:
        return False
    n = re.sub(r"^the\s+", "", name.strip(), flags=re.I).lower()
    if any(n == c.lower() for c in MLB_CLUBS):
        return True
    # "Chicago White Sox organization", "the Padres"
    return any(n.endswith(nick) or f"{nick} organization" in n for nick in _MLB_NICKNAMES) and \
        not re.search(r"(league|association|sky sox|bird dawgs|milkmen|ballers)", n)


def clean_name(raw: str) -> str:
    """Strip position tags, trailing punctuation, and doubled whitespace from a player name."""
    s = raw.strip().strip(".,;:")
    s = POS_PREFIX.sub("", s)
    s = re.sub(r"\s+", " ", s)
    return s


def clean_club(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    s = re.sub(r"^the\s+", "", raw.strip(), flags=re.I).strip(" .,")
    return s or None


def strip_duplicate_lead(line: str) -> str:
    """'Elijah Young Traded Elijah Young to ...' -> 'Traded Elijah Young to ...'."""
    m = re.match(rf"^(?P<lead>[A-Z][\w.'\- ]+?)\s+(?P<rest>{_VERBS}\b.*)$", line)
    if m and not re.match(rf"^{_VERBS}\b", m.group("lead")):
        lead = clean_name(m.group("lead"))
        # Only strip if the same name appears again in the rest, so we never eat a team name.
        if lead and lead.lower() in m.group("rest").lower():
            return m.group("rest")
    return line


def parse_date_header(line: str, season: int) -> Optional[date]:
    """
    Parse 'August 30', 'Aug. 30', 'May 13, 2026'. Lines without a year are placed in the
    season's calendar: October through December belong to the prior year, because a
    season's report runs from the previous fall through September.
    """
    m = re.match(r"^\s*([A-Za-z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,\s*(\d{4}))?\s*$", line)
    if not m:
        return None
    word = m.group(1).lower()
    month = MONTHS.get(word) or MONTH_ABBR.get(word[:4]) or MONTH_ABBR.get(word[:3])
    if not month:
        return None
    day = int(m.group(2))
    if m.group(3):
        year = int(m.group(3))
    else:
        year = season - 1 if month >= 10 else season
    try:
        return date(year, month, day)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------

# Each rule: (txn type, compiled regex). First match wins, so order matters.
# Named groups: name (player), cp (counterparty club).
_RULES: list[tuple[str, re.Pattern]] = [
    # Contract sold or transferred to another club. Usually an MLB org, sometimes Mexico or Japan.
    ("contract_sold", re.compile(r"\b(?:sold|transferred|purchased)\s+the\s+contract\s+of\s+(?P<name>.+?)\s+to\s+(?P<cp>.+?)\.?$", re.I)),
    ("contract_sold", re.compile(r"^(?P<name>.+?)'s\s+contract\s+(?:was\s+)?(?:sold|purchased|transferred)\s+(?:to|by)\s+(?P<cp>.+?)\.?$", re.I)),

    # Releases and waivers
    ("released", re.compile(r"^released\s+(?P<name>.+?)\.?$", re.I)),
    ("released", re.compile(r"^placed\s+(?P<name>.+?)\s+on\s+(?:the\s+)?irrevocable\s+waivers", re.I)),
    ("released", re.compile(r"^(?P<name>.+?)\s+cleared\s+waivers\s+and\s+(?:is|became)\s+a\s+free\s+agent", re.I)),
    ("released", re.compile(r"^(?P<name>.+?)\s+(?:has\s+been|was)\s+released", re.I)),

    # Ineligible list variants
    ("retired",   re.compile(r"^placed\s+(?P<name>.+?)\s+on\s+(?:the\s+)?ineligible\s+list\s*\((?:voluntary\s+)?retire", re.I)),
    ("retired",   re.compile(r"^(?P<name>.+?)\s+(?:has\s+)?retired\b", re.I)),
    ("suspended", re.compile(r"^placed\s+(?P<name>.+?)\s+on\s+(?:the\s+)?ineligible\s+list\s*\(suspen", re.I)),
    ("suspended", re.compile(r"^suspended\s+(?P<name>.+?)(?:\s+for\b.*)?\.?$", re.I)),
    ("other",     re.compile(r"^placed\s+(?P<name>.+?)\s+on\s+(?:the\s+)?ineligible\s+list", re.I)),
    ("other",     re.compile(r"^reinstated\s+(?P<name>.+?)\s+from\s+(?:the\s+)?ineligible\s+list", re.I)),

    # Injury moves
    ("injury", re.compile(r"^placed\s+(?P<name>.+?)\s+on\s+(?:the\s+)?(?:\d+[- ]day\s+)?injur(?:y|ed)\s+list", re.I)),
    ("injury", re.compile(r"^moved\s+(?P<name>.+?)\s+to\s+(?:the\s+)?(?:\d+[- ]day\s+)?injur(?:y|ed)\s+list", re.I)),
    ("injury", re.compile(r"^(?:reinstated|activated)\s+(?P<name>.+?)\s+from\s+(?:the\s+)?(?:\d+[- ]day\s+)?injur(?:y|ed)\s+list", re.I)),
    ("injury", re.compile(r"^removed\s+(?P<name>.+?)\s+from\s+(?:the\s+)?(?:\d+[- ]day\s+)?injur(?:y|ed)\s+list", re.I)),

    # Signings and option pickups
    ("signed", re.compile(r"^(?:signed|re-?signed)\s+(?P<name>.+?)(?:\s+to\s+(?:their|the|a)\b.*)?\.?$", re.I)),
    ("signed", re.compile(r"^exercised\s+the\s+\d{4}\s+contract\s+option\s+(?:for|on)\s+(?P<name>.+?)\.?$", re.I)),

    # Trades, outgoing. Covers "Traded", the "Tradeed" typo, and "<Team> trade X to Y".
    ("traded", re.compile(rf"^(?P<name>.+?)\s+has\s+been\s+traded\s+to\s+(?P<cp>.+?){_CP_TAIL}", re.I)),
    ("traded", re.compile(rf"^(?:.+?\s)?trade(?:e)?[ds]?\s+(?P<name>.+?)\s+to\s+(?P<cp>.+?){_CP_TAIL}", re.I)),

    # Trades and claims, incoming
    ("traded", re.compile(rf"^(?:acquired|received)\s+(?P<name>.+?)\s+from\s+(?P<cp>.+?){_CP_TAIL}", re.I)),
    ("traded", re.compile(r"^claimed\s+(?P<name>.+?)\s+off\s+waivers(?:\s+from\s+(?P<cp>.+?))?\.?$", re.I)),

    # Draft selections
    ("drafted", re.compile(r"^selected\s+(?P<name>.+?)\s+in\s+the\b", re.I)),
]


def classify(line: str) -> tuple[str, Optional[str], Optional[str]]:
    """Return (txn type, player name, counterparty club) for one transaction sentence."""
    text = strip_duplicate_lead(line.strip())
    for txn, rx in _RULES:
        m = rx.search(text)
        if m:
            name = clean_name(m.group("name")) if m.groupdict().get("name") else None
            cp = clean_club(m.groupdict().get("cp"))
            return txn, name, cp
    return "other", None, None


# ---------------------------------------------------------------------------
# Report parser
# ---------------------------------------------------------------------------

def parse_report(lines: Iterable[str], season: int, known_teams: Iterable[str] = ()) -> list[ParsedTxn]:
    """
    Walk the report top to bottom, tracking the current date and team header.

    known_teams helps tell a team header apart from an unbulleted transaction line.
    Without it, any short line that is not a date and does not start with a verb is
    treated as a team header.
    """
    known = {t.lower().replace("-", " ") for t in known_teams}
    current_date: Optional[date] = None
    current_team: Optional[str] = None
    out: list[ParsedTxn] = []

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        d = parse_date_header(line, season)
        if d:
            current_date, current_team = d, None
            continue

        bulleted = bool(BULLET.match(line))
        body = BULLET.sub("", line).strip()
        if not body:
            continue

        looks_like_team = (
            not bulleted
            and (body.lower().replace("-", " ") in known
                 or (len(body.split()) <= 5
                     and not re.match(rf"^{_VERBS}\b", body, re.I)
                     and not re.search(r"\b(?:trade|traded|signed|released|waivers|list|contract)\b", body, re.I)))
        )
        if looks_like_team:
            current_team = body
            continue

        if current_date is None:
            continue   # a line before the first date header, nothing to anchor it to

        txn, name, cp = classify(body)
        t = ParsedTxn(
            txn_date=current_date,
            team=current_team or "",
            raw_text=body,
            txn=txn,
            player_name=name,
            counterparty=cp,
            counterparty_affiliated=is_affiliated_club(cp) if cp else None,
        )
        if txn == "contract_sold" and cp is None:
            t.counterparty_affiliated = True     # "contract purchased" with no club named is an MLB org in practice
        if name is None:
            t.notes.append("no player name found")
        out.append(t)

    return out
