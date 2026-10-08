"""Seed the DEVELOPMENT database with demo users, experiences and behaviour histories.

Run from backend/:
    python -m scripts.seed            # add whatever demo data is missing
    python -m scripts.seed --reset    # also rebuild the demo users' interaction histories

Safety:
  - Refuses to run against any database whose name ends in "_test".
  - Only ever touches its own records: users named "demo_*" and the catalogue
    titles defined below. Nothing else is read for deletion or modified.
  - Re-runnable: users/experiences are get-or-create; a demo user's history is
    only generated if they have none (or with --reset).

Histories are scripted from behaviour profiles (not random noise): a profile
says which categories the person loves, tolerates and avoids, plus their usual
difficulty and budget. A seeded RNG (per username) varies the details, so the
output is the same on every run.
"""

import argparse
import random
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.enums import EventType as E
from app.models import Experience, Interaction, User

DEMO_PREFIX = "demo_"
HISTORY_DAYS = 70

# (title, category, difficulty, duration_minutes, cost in whole rupees, description)
CATALOGUE = [
    ("Sunrise hill hike", "outdoors", "beginner", 150, 0, "A gentle 5 km climb to watch the sunrise from the ridge. Bring water and a torch."),
    ("Lakeside birdwatching walk", "outdoors", "beginner", 120, 200, "Slow morning walk around the lake with a guide who knows the local birds."),
    ("Full-day forest trek", "outdoors", "intermediate", 420, 600, "A 15 km trail through dense forest with a packed lunch by the river."),
    ("Night sky stargazing camp", "outdoors", "intermediate", 600, 1500, "Drive out of the city lights, pitch a tent and learn the constellations."),
    ("Coastal cleanup and beach walk", "outdoors", "beginner", 180, 0, "Join a volunteer crew clearing plastic from the shore, then walk the coast."),
    ("Monsoon waterfall trail", "outdoors", "intermediate", 300, 400, "A muddy, rewarding hike to a seasonal waterfall. Good shoes required."),
    ("Two-day mountain camping trip", "outdoors", "advanced", 2880, 4500, "Carry your own pack to a high-altitude campsite and back over a weekend."),
    ("Indoor rock climbing intro", "adventure", "beginner", 120, 900, "Learn knots, belaying and your first routes on an indoor wall."),
    ("White-water rafting day", "adventure", "intermediate", 360, 2500, "Grade III rapids with a certified guide, safety briefing included."),
    ("Paragliding tandem flight", "adventure", "intermediate", 90, 3500, "Fly with an instructor from a hilltop launch site. No experience needed."),
    ("Cave exploration with a guide", "adventure", "advanced", 300, 2000, "Squeeze, crawl and climb through a limestone cave system with a headlamp."),
    ("Mountain biking downhill trail", "adventure", "advanced", 240, 1800, "Technical descents on a rented full-suspension bike. Helmet provided."),
    ("Zipline and rope course", "adventure", "beginner", 150, 1200, "Treetop rope bridges and a 300 m zipline over the valley."),
    ("Overnight kayaking expedition", "adventure", "advanced", 1440, 5000, "Paddle a river stretch, camp on a sandbank, paddle back at dawn."),
    ("Beginner pottery wheel class", "creative", "beginner", 120, 800, "Centre clay on the wheel and throw your first bowl. Glazing included."),
    ("Watercolour landscapes workshop", "creative", "beginner", 150, 600, "Paint washes, skies and trees with a working illustrator."),
    ("Street photography walk", "creative", "intermediate", 180, 300, "Practise composition and candid shots in the old market with a photographer."),
    ("Write a short story in a weekend", "creative", "intermediate", 600, 0, "A structured prompt-a-day plan to draft, edit and finish one short story."),
    ("Block printing on fabric", "creative", "beginner", 180, 700, "Carve a simple block and print your own tote bag."),
    ("Digital illustration basics", "creative", "intermediate", 240, 500, "Layers, brushes and colour on a tablet, ending with a finished character."),
    ("Build a ceramic mug set", "creative", "advanced", 480, 2200, "Throw, trim and handle a matching set of four mugs across two sessions."),
    ("Board game café evening", "social", "beginner", 180, 300, "Meet new people over strategy and party games. Staff teach the rules."),
    ("Community cooking night", "social", "beginner", 150, 400, "Cook a three-course meal with a group of strangers, then eat it together."),
    ("Pub quiz with strangers", "social", "beginner", 120, 200, "Get placed on a random team and compete for the trivia trophy."),
    ("Salsa dancing for beginners", "social", "beginner", 90, 500, "Basic steps and partner turns. No partner needed; everyone rotates."),
    ("Volunteer at an animal shelter", "social", "beginner", 240, 0, "Walk dogs, socialise cats and help the shelter team for an afternoon."),
    ("Host a neighbourhood potluck", "social", "intermediate", 240, 600, "A checklist for inviting neighbours, planning dishes and running the evening."),
    ("Improv comedy workshop", "social", "intermediate", 150, 700, "Games and scenes that build quick thinking and confidence in a group."),
    ("Intro to Python in one afternoon", "learning", "beginner", 240, 0, "Write and run your first programs: variables, loops and functions."),
    ("Learn 50 phrases in Japanese", "learning", "beginner", 300, 0, "A spaced-repetition plan for the 50 most useful travel phrases."),
    ("Museum history guided tour", "learning", "beginner", 120, 250, "A curator-led tour of the city museum's ancient history galleries."),
    ("Build a weather station with Arduino", "learning", "intermediate", 360, 1800, "Wire sensors, write the firmware and log temperature and humidity."),
    ("Public speaking crash course", "learning", "intermediate", 180, 900, "Structure a talk, handle nerves and deliver a 5-minute speech on video."),
    ("Personal finance fundamentals", "learning", "beginner", 120, 0, "Budgeting, saving and how index funds work, with a worksheet."),
    ("Machine learning study sprint", "learning", "advanced", 720, 0, "A focused plan to implement linear regression and a small neural net from scratch."),
    ("Morning yoga in the park", "wellness", "beginner", 60, 0, "An outdoor community yoga class suitable for complete beginners."),
    ("Guided meditation session", "wellness", "beginner", 30, 150, "A calm 30-minute guided meditation focused on breathing and attention."),
    ("Sound bath relaxation", "wellness", "beginner", 60, 500, "Lie back while singing bowls and gongs guide you into deep relaxation."),
    ("Breathwork for stress", "wellness", "beginner", 45, 300, "Simple breathing techniques you can use before exams or interviews."),
    ("Digital detox day", "wellness", "intermediate", 480, 0, "A full day plan without screens: walks, reading, journaling and cooking."),
    ("Pilates core workshop", "wellness", "intermediate", 75, 600, "Strengthen your core with mat-based Pilates in a small group."),
    ("Silent retreat weekend", "wellness", "advanced", 2880, 6000, "Two days of silence, meditation and simple meals at a retreat centre."),
]

LEVELS = {"beginner": 0, "intermediate": 1, "advanced": 2}


@dataclass(frozen=True)
class Profile:
    username: str
    loves: list[str]                 # explores deeply: view, click, save, like, complete
    tolerates: list[str] = field(default_factory=list)  # browses: view, click, sometimes save
    avoids: list[str] = field(default_factory=list)     # views then skips or dislikes
    difficulty: str = "beginner"
    budget: int = 1000
    searches: list[str] = field(default_factory=list)
    loved_items: int = 5


PROFILES = [
    Profile("demo_outdoor_maya", ["outdoors"], ["adventure"], ["social"], "intermediate", 1500,
            ["weekend trek near the city"], 6),
    Profile("demo_adventure_arjun", ["adventure"], ["outdoors"], ["wellness"], "advanced", 5000,
            ["adrenaline activities"], 6),
    Profile("demo_creative_lena", ["creative"], ["learning"], ["adventure"], "beginner", 900,
            ["pottery class for beginners"], 5),
    Profile("demo_creative_ravi", ["creative"], ["social"], ["outdoors"], "intermediate", 2500,
            ["photography walk"], 5),
    Profile("demo_social_zara", ["social"], ["creative"], ["learning"], "beginner", 700,
            ["things to do with friends tonight"], 5),
    Profile("demo_social_kabir", ["social"], ["adventure"], ["wellness"], "intermediate", 800,
            ["meet new people"], 5),
    Profile("demo_wellness_anika", ["wellness"], ["outdoors"], ["adventure"], "beginner", 600,
            ["relaxing and cheap"], 5),
    Profile("demo_wellness_tom", ["wellness"], ["learning"], ["social"], "intermediate", 1000,
            ["stress relief"], 5),
    Profile("demo_learning_sofia", ["learning"], ["creative"], ["social"], "beginner", 500,
            ["learn coding"], 5),
    Profile("demo_learning_dev", ["learning"], ["wellness"], ["adventure"], "advanced", 2000,
            ["electronics project"], 5),
    Profile("demo_mixed_noah", ["outdoors", "creative", "learning"], [], [], "beginner", 800,
            ["something new this weekend"], 2),
    Profile("demo_mixed_priya", ["social", "wellness", "adventure"], [], [], "intermediate", 2500,
            ["fun and active"], 2),
    Profile("demo_coldstart_ella", []),   # no history: cold-start user
    Profile("demo_coldstart_omar", []),   # no history: cold-start user
]


def check_target_database(url: str) -> str:
    """Return the database name, or exit if it looks like a test database."""
    name = make_url(url).database or ""
    if name.endswith("_test"):
        sys.exit(f"Refusing to seed '{name}': the seed script is for the development database only.")
    return name


def _pick(rng: random.Random, pool: list[Experience], profile: Profile, n: int) -> list[Experience]:
    """The n experiences in pool that best fit the profile's level and budget."""
    want = LEVELS[profile.difficulty]
    ranked = sorted(
        pool,
        key=lambda e: (e.cost > profile.budget, abs(LEVELS.get(e.difficulty, 1) - want), rng.random()),
    )
    return ranked[:n]


def build_history(profile: Profile, by_category: dict[str, list[Experience]], now: datetime) -> list[Interaction]:
    """Turn a behaviour profile into a believable, time-ordered list of events."""
    rng = random.Random(profile.username)
    plan: list[tuple[str, Experience]] = []
    for category in profile.loves:
        plan += [("love", e) for e in _pick(rng, by_category[category], profile, profile.loved_items)]
    for category in profile.tolerates:
        plan += [("tolerate", e) for e in rng.sample(by_category[category], 2)]
    for category in profile.avoids:
        plan += [("avoid", e) for e in rng.sample(by_category[category], 2)]
    rng.shuffle(plan)

    events: list[Interaction] = []
    start = now - timedelta(days=HISTORY_DAYS)
    gap = timedelta(days=HISTORY_DAYS - 5) / max(len(plan), 1)
    latest = now - timedelta(hours=1)

    def add(event_type: E, at: datetime, experience: Experience | None = None, query: str | None = None):
        events.append(Interaction(
            user_id=None,  # filled in by the caller
            experience_id=experience.id if experience else None,
            event_type=event_type,
            query_text=query,
            properties={"source": "seed"},
            occurred_at=min(at, latest),
        ))

    for i, (attitude, exp) in enumerate(plan):
        t = start + gap * i + timedelta(hours=rng.randint(0, 20))
        if i == 0 and profile.searches:
            add(E.SEARCH, t - timedelta(minutes=5), query=profile.searches[0])
        add(E.VIEW, t, exp)
        if attitude == "avoid":
            add(E.SKIP if rng.random() < 0.7 else E.DISLIKE, t + timedelta(seconds=40), exp)
            continue
        add(E.CLICK, t + timedelta(minutes=1), exp)
        if attitude == "tolerate":
            if rng.random() < 0.35:
                add(E.SAVE, t + timedelta(minutes=3), exp)
            continue
        # loved
        if rng.random() < 0.85:
            add(E.SAVE, t + timedelta(minutes=3), exp)
            if rng.random() < 0.2:  # changed their mind
                add(E.UNSAVE, t + timedelta(days=rng.randint(1, 3)), exp)
                continue
            if rng.random() < 0.7:
                add(E.LIKE, t + timedelta(minutes=5), exp)
            if rng.random() < 0.55:
                add(E.COMPLETE, t + timedelta(days=rng.randint(2, 9)), exp)

    return sorted(events, key=lambda ev: ev.occurred_at)


def seed(db: Session, now: datetime, reset: bool = False) -> dict[str, int]:
    """Create missing demo data. Returns counts of what was created."""
    created = {"users": 0, "experiences": 0, "interactions": 0, "histories_rebuilt": 0}

    # Experiences: get-or-create by title, with created_at spread over ~4 months for freshness.
    existing = {e.title: e for e in db.scalars(select(Experience).where(
        Experience.title.in_([c[0] for c in CATALOGUE])))}
    for i, (title, category, difficulty, duration, cost, description) in enumerate(CATALOGUE):
        if title not in existing:
            exp = Experience(title=title, category=category, difficulty=difficulty,
                             duration_minutes=duration, cost=cost, description=description,
                             created_at=now - timedelta(days=(i * 7) % 120))
            db.add(exp)
            existing[title] = exp
            created["experiences"] += 1
    db.flush()

    by_category: dict[str, list[Experience]] = {}
    for title, category, *_ in CATALOGUE:
        by_category.setdefault(category, []).append(existing[title])

    # Users: get-or-create by username.
    users = {u.username: u for u in db.scalars(select(User).where(User.username.like(f"{DEMO_PREFIX}%")))}
    for profile in PROFILES:
        if profile.username not in users:
            users[profile.username] = User(username=profile.username)
            db.add(users[profile.username])
            created["users"] += 1
    db.flush()

    # Histories: only for demo users without any events, unless --reset.
    for profile in PROFILES:
        user = users[profile.username]
        if reset:
            db.execute(delete(Interaction).where(Interaction.user_id == user.id))
        has_events = db.scalar(select(func.count()).where(Interaction.user_id == user.id))
        if has_events:
            continue
        events = build_history(profile, by_category, now)
        for ev in events:
            ev.user_id = user.id
        db.add_all(events)
        created["interactions"] += len(events)
        created["histories_rebuilt"] += bool(events) and reset

    db.commit()
    return created


def print_summary(db: Session) -> None:
    demo_users = db.scalars(select(User).where(User.username.like(f"{DEMO_PREFIX}%")).order_by(User.id)).all()
    print(f"\n{'user':24} {'id':>4} {'events':>7}  top categories (positive events)")
    for u in demo_users:
        n = db.scalar(select(func.count()).where(Interaction.user_id == u.id))
        top = db.execute(
            select(Experience.category, func.count())
            .join(Interaction, Interaction.experience_id == Experience.id)
            .where(Interaction.user_id == u.id,
                   Interaction.event_type.in_([E.SAVE, E.LIKE, E.COMPLETE]))
            .group_by(Experience.category).order_by(func.count().desc(), Experience.category)
        ).all()
        label = ", ".join(f"{c} {n}" for c, n in top[:3]) or "(none: cold start)"
        print(f"{u.username:24} {u.id:>4} {n:>7}  {label}")
    totals = {name: db.scalar(select(func.count()).select_from(model))
              for name, model in [("users", User), ("experiences", Experience), ("interactions", Interaction)]}
    print(f"\ndatabase totals: {totals}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="rebuild demo users' interaction histories")
    args = parser.parse_args()

    name = check_target_database(settings.DATABASE_URL)
    print(f"Seeding database '{name}'" + (" (resetting demo histories)" if args.reset else ""))
    with SessionLocal() as db:
        created = seed(db, now=datetime.now(timezone.utc), reset=args.reset)
        print("created:", created)
        print_summary(db)


if __name__ == "__main__":
    main()
