from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import sqlite3
from typing import Iterator

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.models import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _build_engine(database_url: str) -> Engine:
    if database_url.startswith("sqlite"):
        return create_engine(
            database_url,
            pool_pre_ping=True,
            connect_args={"check_same_thread": False},
            future=True,
        )

    return create_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
        pool_recycle=settings.db_pool_recycle,
        future=True,
    )


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


_ENGINE = _build_engine(settings.database_url)
SessionLocal = sessionmaker(
    bind=_ENGINE,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
    future=True,
)


def get_engine() -> Engine:
    return _ENGINE


def reset_database_engine(database_url: str | None = None) -> None:
    global _ENGINE
    if database_url:
        object.__setattr__(settings, "database_url", database_url)

    _ENGINE.dispose()
    _ENGINE = _build_engine(settings.database_url)
    SessionLocal.configure(bind=_ENGINE)


@contextmanager
def get_db() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_db_connection() -> None:
    with _ENGINE.connect() as connection:
        connection.execute(text("SELECT 1"))


def init_db() -> None:
    Base.metadata.create_all(bind=_ENGINE)


def seed_sample_words_if_empty() -> int:
    sample_words = [
        # ── A1 — Beginner (30 words) ────────────────────────────────
        ("привіт", "hello", "A1"),
        ("так", "yes", "A1"),
        ("ні", "no", "A1"),
        ("дякую", "thank you", "A1"),
        ("будь ласка", "please", "A1"),
        ("вода", "water", "A1"),
        ("хліб", "bread", "A1"),
        ("молоко", "milk", "A1"),
        ("яблуко", "apple", "A1"),
        ("кіт", "cat", "A1"),
        ("собака", "dog", "A1"),
        ("будинок", "house", "A1"),
        ("день", "day", "A1"),
        ("ніч", "night", "A1"),
        ("мама", "mother", "A1"),
        ("тато", "father", "A1"),
        ("дитина", "child", "A1"),
        ("один", "one", "A1"),
        ("два", "two", "A1"),
        ("три", "three", "A1"),
        ("великий", "big", "A1"),
        ("малий", "small", "A1"),
        ("добрий", "good", "A1"),
        ("поганий", "bad", "A1"),
        ("їжа", "food", "A1"),
        ("школа", "school", "A1"),
        ("друг", "friend", "A1"),
        ("ім'я", "name", "A1"),
        ("місто", "city", "A1"),
        ("країна", "country", "A1"),
        # ── A2 — Elementary (30 words) ──────────────────────────────
        ("добрий ранок", "good morning", "A2"),
        ("на добраніч", "good night", "A2"),
        ("сім'я", "family", "A2"),
        ("книга", "book", "A2"),
        ("стіл", "table", "A2"),
        ("стілець", "chair", "A2"),
        ("вікно", "window", "A2"),
        ("двері", "door", "A2"),
        ("машина", "car", "A2"),
        ("любов", "love", "A2"),
        ("час", "time", "A2"),
        ("робота", "work", "A2"),
        ("гроші", "money", "A2"),
        ("магазин", "shop", "A2"),
        ("лікар", "doctor", "A2"),
        ("вчитель", "teacher", "A2"),
        ("музика", "music", "A2"),
        ("фільм", "movie", "A2"),
        ("погода", "weather", "A2"),
        ("дощ", "rain", "A2"),
        ("сонце", "sun", "A2"),
        ("подорож", "journey", "A2"),
        ("квитки", "tickets", "A2"),
        ("сніданок", "breakfast", "A2"),
        ("обід", "lunch", "A2"),
        ("вечеря", "dinner", "A2"),
        ("дорога", "road", "A2"),
        ("тварина", "animal", "A2"),
        ("квітка", "flower", "A2"),
        ("дерево", "tree", "A2"),
        # ── B1 — Intermediate (30 words) ────────────────────────────
        ("незважаючи на", "despite", "B1"),
        ("однак", "however", "B1"),
        ("отже", "therefore", "B1"),
        ("насправді", "actually", "B1"),
        ("очевидно", "obviously", "B1"),
        ("можливо", "perhaps", "B1"),
        ("зрештою", "eventually", "B1"),
        ("здебільшого", "mostly", "B1"),
        ("зазвичай", "usually", "B1"),
        ("визначати", "determine", "B1"),
        ("досягати", "achieve", "B1"),
        ("порівнювати", "compare", "B1"),
        ("враження", "impression", "B1"),
        ("досвід", "experience", "B1"),
        ("середовище", "environment", "B1"),
        ("розвиток", "development", "B1"),
        ("суспільство", "society", "B1"),
        ("уряд", "government", "B1"),
        ("освіта", "education", "B1"),
        ("наука", "science", "B1"),
        ("технологія", "technology", "B1"),
        ("здоров'я", "health", "B1"),
        ("подорожувати", "travel", "B1"),
        ("пояснювати", "explain", "B1"),
        ("пропонувати", "suggest", "B1"),
        ("вирішувати", "decide", "B1"),
        ("помилка", "mistake", "B1"),
        ("успіх", "success", "B1"),
        ("різниця", "difference", "B1"),
        ("важливий", "important", "B1"),
        # ── B2 — Upper Intermediate (30 words) ──────────────────────
        ("впливати", "influence", "B2"),
        ("забезпечувати", "provide", "B2"),
        ("розглядати", "consider", "B2"),
        ("стверджувати", "claim", "B2"),
        ("підтримувати", "maintain", "B2"),
        ("нести відповідальність", "responsibility", "B2"),
        ("обставини", "circumstances", "B2"),
        ("наслідки", "consequences", "B2"),
        ("сприяти", "contribute", "B2"),
        ("дослідження", "research", "B2"),
        ("значний", "significant", "B2"),
        ("доступний", "available", "B2"),
        ("ефективний", "efficient", "B2"),
        ("загрозливий", "threatening", "B2"),
        ("суперечливий", "controversial", "B2"),
        ("висновок", "conclusion", "B2"),
        ("свідомість", "awareness", "B2"),
        ("прибуток", "profit", "B2"),
        ("конкуренція", "competition", "B2"),
        ("стратегія", "strategy", "B2"),
        ("аналізувати", "analyze", "B2"),
        ("оцінювати", "evaluate", "B2"),
        ("реагувати", "react", "B2"),
        ("передбачати", "predict", "B2"),
        ("перевага", "advantage", "B2"),
        ("нерівність", "inequality", "B2"),
        ("промисловість", "industry", "B2"),
        ("виробництво", "production", "B2"),
        ("споживач", "consumer", "B2"),
        ("ресурс", "resource", "B2"),
        # ── C1 — Advanced (30 words) ────────────────────────────────
        ("відшкодування", "compensation", "C1"),
        ("обґрунтовувати", "substantiate", "C1"),
        ("передумова", "prerequisite", "C1"),
        ("невід'ємний", "inherent", "C1"),
        ("двозначність", "ambiguity", "C1"),
        ("протиріччя", "contradiction", "C1"),
        ("наполегливість", "perseverance", "C1"),
        ("перешкода", "impediment", "C1"),
        ("виправдовувати", "justify", "C1"),
        ("зобов'язання", "obligation", "C1"),
        ("підпорядкований", "subordinate", "C1"),
        ("доцільний", "expedient", "C1"),
        ("розбіжність", "discrepancy", "C1"),
        ("всебічний", "comprehensive", "C1"),
        ("поступовий", "gradual", "C1"),
        ("неминучий", "inevitable", "C1"),
        ("упередження", "prejudice", "C1"),
        ("виснажливий", "exhausting", "C1"),
        ("вразливий", "vulnerable", "C1"),
        ("цілісність", "integrity", "C1"),
        ("нюанс", "nuance", "C1"),
        ("парадокс", "paradox", "C1"),
        ("скептицизм", "skepticism", "C1"),
        ("прагматичний", "pragmatic", "C1"),
        ("автономний", "autonomous", "C1"),
        ("ієрархія", "hierarchy", "C1"),
        ("контекст", "context", "C1"),
        ("кореляція", "correlation", "C1"),
        ("тенденція", "tendency", "C1"),
        ("динаміка", "dynamics", "C1"),
        # ── C2 — Mastery (30 words) ─────────────────────────────────
        ("безпрецедентний", "unprecedented", "C2"),
        ("недоторканність", "inviolability", "C2"),
        ("маніпулювання", "manipulation", "C2"),
        ("юриспруденція", "jurisprudence", "C2"),
        ("ефемерний", "ephemeral", "C2"),
        ("квінтесенція", "quintessence", "C2"),
        ("антагоністичний", "antagonistic", "C2"),
        ("ідіосинкразія", "idiosyncrasy", "C2"),
        ("екстраполювати", "extrapolate", "C2"),
        ("сублімація", "sublimation", "C2"),
        ("трансцендентний", "transcendent", "C2"),
        ("когерентність", "coherence", "C2"),
        ("дихотомія", "dichotomy", "C2"),
        ("ретроспективний", "retrospective", "C2"),
        ("гомогенний", "homogeneous", "C2"),
        ("іманентний", "immanent", "C2"),
        ("синергія", "synergy", "C2"),
        ("репрезентативний", "representative", "C2"),
        ("перипетія", "vicissitude", "C2"),
        ("конотація", "connotation", "C2"),
        ("аксіома", "axiom", "C2"),
        ("детермінізм", "determinism", "C2"),
        ("амбівалентний", "ambivalent", "C2"),
        ("прерогатива", "prerogative", "C2"),
        ("рудиментарний", "rudimentary", "C2"),
        ("фундаментальний", "fundamental", "C2"),
        ("мікрокосм", "microcosm", "C2"),
        ("макрокосм", "macrocosm", "C2"),
        ("абстракція", "abstraction", "C2"),
        ("тривіальний", "trivial", "C2"),
    ]

    with get_db() as session:
        count = session.execute(text("SELECT COUNT(*) FROM words")).scalar_one()
        if count > 0:
            return 0

        session.execute(
            text("INSERT INTO words (id, ua, en, level) VALUES (:id, :ua, :en, :level)"),
            [
                {"id": f"seed-{idx:03d}", "ua": ua, "en": en, "level": level}
                for idx, (ua, en, level) in enumerate(sample_words, start=1)
            ],
        )

    return len(sample_words)


def clear_expired_llm_cache() -> None:
    with get_db() as session:
        session.execute(
            text("DELETE FROM llm_cache WHERE expires_at <= :now"),
            {"now": _utc_now()},
        )
