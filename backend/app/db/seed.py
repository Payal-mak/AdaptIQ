"""Insert the interview topics. Safe to run more than once: run `python -m app.db.seed`."""

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_engine
from app.models import Topic

TOPICS: dict[str, str] = {
    "DBMS": "Database management systems: SQL, normalization, transactions, indexing.",
    "OS": "Operating systems: processes, threads, scheduling, memory, deadlocks.",
    "Computer Networks": "Networking: OSI/TCP-IP, protocols, routing, HTTP, DNS.",
    "OOP": "Object-oriented programming: classes, inheritance, polymorphism, design.",
    "DSA": "Data structures and algorithms: complexity, trees, graphs, sorting.",
    "Java": "Java language and core libraries.",
    "Python": "Python language and core libraries.",
    "HR": "Behavioural and HR interview questions.",
}


def seed_topics(db: Session) -> int:
    """Add any missing topics. Returns how many were added."""
    existing = set(db.scalars(select(Topic.name)))
    added = 0
    for name, description in TOPICS.items():
        if name not in existing:
            db.add(Topic(name=name, description=description))
            added += 1
    db.commit()
    return added


if __name__ == "__main__":
    with sessionmaker(bind=get_engine())() as session:
        print(f"Added {seed_topics(session)} topic(s).")
