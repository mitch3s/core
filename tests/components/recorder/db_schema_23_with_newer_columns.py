"""Models for SQLAlchemy.

This file contains the model definitions for schema version 23
used by Home Assistant Core 2021.11.0, which adds the name column
to statistics_meta.

The v23 schema as been slightly modified to add the EventData table to
allow the recorder to startup successfully.

It is used to test the schema migration logic.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import json
import logging
import time
from typing import TypedDict, overload

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    LargeBinary,
    SmallInteger,
    String,
    Text,
    distinct,
)
from sqlalchemy.dialects import mysql, oracle, postgresql
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.orm.session import Session

from homeassistant.const import (
    MAX_LENGTH_EVENT_CONTEXT_ID,
    MAX_LENGTH_EVENT_EVENT_TYPE,
    MAX_LENGTH_EVENT_ORIGIN,
    MAX_LENGTH_STATE_DOMAIN,
    MAX_LENGTH_STATE_ENTITY_ID,
    MAX_LENGTH_STATE_STATE,
)
from homeassistant.core import Context, Event, EventOrigin, State, split_entity_id
from homeassistant.helpers.json import JSONEncoder
import homeassistant.util.dt as dt_util

# SQLAlchemy Schema
Base = declarative_base()

SCHEMA_VERSION = 23

_LOGGER = logging.getLogger(__name__)

DB_TIMEZONE = "+00:00"

TABLE_EVENTS = "events"
TABLE_STATES = "states"
TABLE_STATES_META = "states_meta"
TABLE_RECORDER_RUNS = "recorder_runs"
TABLE_SCHEMA_CHANGES = "schema_changes"
TABLE_STATISTICS = "statistics"
TABLE_STATISTICS_META = "statistics_meta"
TABLE_STATISTICS_RUNS = "statistics_runs"
TABLE_STATISTICS_SHORT_TERM = "statistics_short_term"
TABLE_EVENT_DATA = "event_data"
TABLE_EVENT_TYPES = "event_types"

ALL_TABLES = [
    TABLE_STATES,
    TABLE_STATES_META,
    TABLE_EVENTS,
    TABLE_EVENT_TYPES,
    TABLE_RECORDER_RUNS,
    TABLE_SCHEMA_CHANGES,
    TABLE_STATISTICS,
    TABLE_STATISTICS_META,
    TABLE_STATISTICS_RUNS,
    TABLE_STATISTICS_SHORT_TERM,
]

DATETIME_TYPE = DateTime(timezone=True).with_variant(
    mysql.DATETIME(timezone=True, fsp=6), "mysql"
)
DOUBLE_TYPE = (
    Float()
    .with_variant(mysql.DOUBLE(asdecimal=False), "mysql")
    .with_variant(oracle.DOUBLE_PRECISION(), "oracle")
    .with_variant(postgresql.DOUBLE_PRECISION(), "postgresql")
)

TIMESTAMP_TYPE = DOUBLE_TYPE

CONTEXT_ID_BIN_MAX_LENGTH = 16
EVENTS_CONTEXT_ID_BIN_INDEX = "ix_events_context_id_bin"
STATES_CONTEXT_ID_BIN_INDEX = "ix_states_context_id_bin"


class Events(Base):  # type: ignore
    """Event history data."""

    __table_args__ = (
        # Used for fetching events at a specific time
        # see logbook
        Index("ix_events_event_type_time_fired", "event_type", "time_fired"),
        Index(
            EVENTS_CONTEXT_ID_BIN_INDEX,
            "context_id_bin",
            mysql_length=CONTEXT_ID_BIN_MAX_LENGTH,
            mariadb_length=CONTEXT_ID_BIN_MAX_LENGTH,
        ),
        {"mysql_default_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )
    __tablename__ = TABLE_EVENTS
    event_id = Column(Integer, Identity(), primary_key=True)
    event_type = Column(String(MAX_LENGTH_EVENT_EVENT_TYPE))
    event_data = Column(Text().with_variant(mysql.LONGTEXT, "mysql"))
    origin = Column(String(MAX_LENGTH_EVENT_ORIGIN))
    origin_idx = Column(
        SmallInteger
    )  # *** Not originally in v23, only added for recorder to startup ok
    time_fired = Column(DATETIME_TYPE, index=True)
    time_fired_ts = Column(
        TIMESTAMP_TYPE, index=True
    )  # *** Not originally in v23, only added for recorder to startup ok
    created = Column(DATETIME_TYPE, default=dt_util.utcnow)
    context_id = Column(String(MAX_LENGTH_EVENT_CONTEXT_ID), index=True)
    context_user_id = Column(String(MAX_LENGTH_EVENT_CONTEXT_ID), index=True)
    context_parent_id = Column(String(MAX_LENGTH_EVENT_CONTEXT_ID), index=True)
    data_id = Column(
        Integer, ForeignKey("event_data.data_id"), index=True
    )  # *** Not originally in v23, only added for recorder to startup ok
    context_id_bin = Column(
        LargeBinary(CONTEXT_ID_BIN_MAX_LENGTH)
    )  # *** Not originally in v23, only added for recorder to startup ok
    context_user_id_bin = Column(
        LargeBinary(CONTEXT_ID_BIN_MAX_LENGTH)
    )  # *** Not originally in v23, only added for recorder to startup ok
    context_parent_id_bin = Column(
        LargeBinary(CONTEXT_ID_BIN_MAX_LENGTH)
    )  # *** Not originally in v23, only added for recorder to startup ok
    event_type_id = Column(
        Integer, ForeignKey("event_types.event_type_id"), index=True
    )  # *** Not originally in v23, only added for recorder to startup ok
    event_data_rel = relationship(
        "EventData"
    )  # *** Not originally in v23, only added for recorder to startup ok
    event_type_rel = relationship("EventTypes")

    def __repr__(self) -> str:
        """Return string representation of instance for debugging."""
        return (
            f"<recorder.Events("
            f"id={self.event_id}, type='{self.event_type}', data='{self.event_data}', "
            f"origin='{self.origin}', time_fired='{self.time_fired}'"
            f")>"
        )

    @staticmethod
    def from_event(event, event_data=None):
        """Create an event database object from a native event."""
        return Events(
            event_type=event.event_type,
            event_data=event_data
            or json.dumps(event.data, cls=JSONEncoder, separators=(",", ":")),
            origin=str(event.origin.value),
            time_fired=event.time_fired,
            context_id=event.context.id,
            context_user_id=event.context.user_id,
            context_parent_id=event.context.parent_id,
        )

    def to_native(self, validate_entity_id=True):
        """Convert to a native HA Event."""
        context = Context(
            id=self.context_id,
            user_id=self.context_user_id,
            parent_id=self.context_parent_id,
        )
        try:
            return Event(
                self.event_type,
                json.loads(self.event_data),
                EventOrigin(self.origin),
                process_timestamp(self.time_fired),
                context=context,
            )
        except ValueError:
            # When json.loads fails
            _LOGGER.exception("Error converting to event: %s", self)
            return None


# *** Not originally in v23, only added for recorder to startup ok
# This is not being tested by the v23 statistics migration tests
class EventData(Base):  # type: ignore[misc,valid-type]
    """Event data history."""

    __table_args__ = (
        {"mysql_default_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )
    __tablename__ = TABLE_EVENT_DATA
    data_id = Column(Integer, Identity(), primary_key=True)
    hash = Column(BigInteger, index=True)
    # Note that this is not named attributes to avoid confusion with the states table
    shared_data = Column(Text().with_variant(mysql.LONGTEXT, "mysql"))


# *** Not originally in v23, only added for recorder to startup ok
# This is not being tested by the v23 statistics migration tests
class EventTypes(Base):  # type: ignore[misc,valid-type]
    """Event type history."""

    __table_args__ = (
        {"mysql_default_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )
    __tablename__ = TABLE_EVENT_TYPES
    event_type_id = Column(Integer, Identity(), primary_key=True)
    event_type = Column(String(MAX_LENGTH_EVENT_EVENT_TYPE))


class States(Base):  # type: ignore
    """State change history."""

    __table_args__ = (
        # Used for fetching the state of entities at a specific time
        # (get_states in history.py)
        Index("ix_states_entity_id_last_updated", "entity_id", "last_updated"),
        Index(
            STATES_CONTEXT_ID_BIN_INDEX,
            "context_id_bin",
            mysql_length=CONTEXT_ID_BIN_MAX_LENGTH,
            mariadb_length=CONTEXT_ID_BIN_MAX_LENGTH,
        ),
        {"mysql_default_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )
    __tablename__ = TABLE_STATES
    state_id = Column(Integer, Identity(), primary_key=True)
    domain = Column(String(MAX_LENGTH_STATE_DOMAIN))
    entity_id = Column(String(MAX_LENGTH_STATE_ENTITY_ID))
    state = Column(String(MAX_LENGTH_STATE_STATE))
    attributes = Column(Text().with_variant(mysql.LONGTEXT, "mysql"))
    event_id = Column(
        Integer, ForeignKey("events.event_id", ondelete="CASCADE"), index=True
    )
    last_changed = Column(DATETIME_TYPE, default=dt_util.utcnow)
    last_updated_ts = Column(
        TIMESTAMP_TYPE, default=time.time
    )  # *** Not originally in v23, only added for recorder to startup ok
    last_updated = Column(DATETIME_TYPE, default=dt_util.utcnow, index=True)
    last_updated_ts = Column(
        TIMESTAMP_TYPE, default=time.time, index=True
    )  # *** Not originally in v23, only added for recorder to startup ok
    created = Column(DATETIME_TYPE, default=dt_util.utcnow)
    old_state_id = Column(Integer, ForeignKey("states.state_id"), index=True)
    context_id_bin = Column(
        LargeBinary(CONTEXT_ID_BIN_MAX_LENGTH)
    )  # *** Not originally in v23, only added for recorder to startup ok
    context_user_id_bin = Column(
        LargeBinary(CONTEXT_ID_BIN_MAX_LENGTH)
    )  # *** Not originally in v23, only added for recorder to startup ok
    context_parent_id_bin = Column(
        LargeBinary(CONTEXT_ID_BIN_MAX_LENGTH)
    )  # *** Not originally in v23, only added for recorder to startup ok
    metadata_id = Column(
        Integer, ForeignKey("states_meta.metadata_id"), index=True
    )  # *** Not originally in v23, only added for recorder to startup ok
    states_meta_rel = relationship("StatesMeta")
    event = relationship("Events", uselist=False)
    old_state = relationship("States", remote_side=[state_id])

    def __repr__(self) -> str:
        """Return string representation of instance for debugging."""
        return (
            f"<recorder.States("
            f"id={self.state_id}, domain='{self.domain}', entity_id='{self.entity_id}', "
            f"state='{self.state}', event_id='{self.event_id}', "
            f"last_updated='{self.last_updated.isoformat(sep=' ', timespec='seconds')}', "
            f"old_state_id={self.old_state_id}"
            f")>"
        )

    @staticmethod
    def from_event(event):
        """Create object from a state_changed event."""
        entity_id = event.data["entity_id"]
        state = event.data.get("new_state")

        dbstate = States(entity_id=entity_id)

        # State got deleted
        if state is None:
            dbstate.state = ""
            dbstate.domain = split_entity_id(entity_id)[0]
            dbstate.attributes = "{}"
            dbstate.last_changed = event.time_fired
            dbstate.last_updated = event.time_fired
        else:
            dbstate.domain = state.domain
            dbstate.state = state.state
            dbstate.attributes = json.dumps(
                dict(state.attributes), cls=JSONEncoder, separators=(",", ":")
            )
            dbstate.last_changed = state.last_changed
            dbstate.last_updated = state.last_updated

        return dbstate

    def to_native(self, validate_entity_id=True):
        """Convert to an HA state object."""
        try:
            return State(
                self.entity_id,
                self.state,
                json.loads(self.attributes),
                process_timestamp(self.last_changed),
                process_timestamp(self.last_updated),
                # Join the events table on event_id to get the context instead
                # as it will always be there for state_changed events
                context=Context(id=None),
                validate_entity_id=validate_entity_id,
            )
        except ValueError:
            # When json.loads fails
            _LOGGER.exception("Error converting row to state: %s", self)
            return None


# *** Not originally in v23, only added for recorder to startup ok
# This is not being tested by the v23 statistics migration tests
class StatesMeta(Base):  # type: ignore[misc,valid-type]
    """Metadata for states."""

    __table_args__ = (
        {"mysql_default_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )
    __tablename__ = TABLE_STATES_META
    metadata_id = Column(Integer, Identity(), primary_key=True)
    entity_id = Column(String(MAX_LENGTH_STATE_ENTITY_ID))

    def __repr__(self) -> str:
        """Return string representation of instance for debugging."""
        return (
            "<recorder.StatesMeta("
            f"id={self.metadata_id}, entity_id='{self.entity_id}'"
            ")>"
        )


class StatisticResult(TypedDict):
    """Statistic result data class.

    Allows multiple datapoints for the same statistic_id.
    """

    meta: StatisticMetaData
    stat: StatisticData


class StatisticDataBase(TypedDict):
    """Mandatory fields for statistic data class."""

    start: datetime


class StatisticData(StatisticDataBase, total=False):
    """Statistic data class."""

    mean: float
    min: float
    max: float
    last_reset: datetime | None
    state: float
    sum: float


class StatisticsBase:
    """Statistics base class."""

    id = Column(Integer, Identity(), primary_key=True)
    created = Column(DATETIME_TYPE, default=dt_util.utcnow)

    @declared_attr
    def metadata_id(self):
        """Define the metadata_id column for sub classes."""
        return Column(
            Integer,
            ForeignKey(f"{TABLE_STATISTICS_META}.id", ondelete="CASCADE"),
            index=True,
        )

    start = Column(DATETIME_TYPE, index=True)
    mean = Column(DOUBLE_TYPE)
    min = Column(DOUBLE_TYPE)
    max = Column(DOUBLE_TYPE)
    last_reset = Column(DATETIME_TYPE)
    state = Column(DOUBLE_TYPE)
    sum = Column(DOUBLE_TYPE)

    @classmethod
    def from_stats(cls, metadata_id: int, stats: StatisticData):
        """Create object from a statistics."""
        return cls(  # type: ignore
            metadata_id=metadata_id,
            **stats,
        )


class Statistics(Base, StatisticsBase):  # type: ignore
    """Long term statistics."""

    duration = timedelta(hours=1)

    __table_args__ = (
        # Used for fetching statistics for a certain entity at a specific time
        Index("ix_statistics_statistic_id_start", "metadata_id", "start"),
    )
    __tablename__ = TABLE_STATISTICS


class StatisticsShortTerm(Base, StatisticsBase):  # type: ignore
    """Short term statistics."""

    duration = timedelta(minutes=5)

    __table_args__ = (
        # Used for fetching statistics for a certain entity at a specific time
        Index("ix_statistics_short_term_statistic_id_start", "metadata_id", "start"),
    )
    __tablename__ = TABLE_STATISTICS_SHORT_TERM


class StatisticMetaData(TypedDict):
    """Statistic meta data class."""

    has_mean: bool
    has_sum: bool
    name: str | None
    source: str
    statistic_id: str
    unit_of_measurement: str | None


class StatisticsMeta(Base):  # type: ignore
    """Statistics meta data."""

    __table_args__ = (
        {"mysql_default_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )
    __tablename__ = TABLE_STATISTICS_META
    id = Column(Integer, Identity(), primary_key=True)
    statistic_id = Column(String(255), index=True)
    source = Column(String(32))
    unit_of_measurement = Column(String(255))
    has_mean = Column(Boolean)
    has_sum = Column(Boolean)
    name = Column(String(255))

    @staticmethod
    def from_meta(meta: StatisticMetaData) -> StatisticsMeta:
        """Create object from meta data."""
        return StatisticsMeta(**meta)


class RecorderRuns(Base):  # type: ignore
    """Representation of recorder run."""

    __table_args__ = (Index("ix_recorder_runs_start_end", "start", "end"),)
    __tablename__ = TABLE_RECORDER_RUNS
    run_id = Column(Integer, Identity(), primary_key=True)
    start = Column(DateTime(timezone=True), default=dt_util.utcnow)
    end = Column(DateTime(timezone=True))
    closed_incorrect = Column(Boolean, default=False)
    created = Column(DateTime(timezone=True), default=dt_util.utcnow)

    def __repr__(self) -> str:
        """Return string representation of instance for debugging."""
        end = (
            f"'{self.end.isoformat(sep=' ', timespec='seconds')}'" if self.end else None
        )
        return (
            f"<recorder.RecorderRuns("
            f"id={self.run_id}, start='{self.start.isoformat(sep=' ', timespec='seconds')}', "
            f"end={end}, closed_incorrect={self.closed_incorrect}, "
            f"created='{self.created.isoformat(sep=' ', timespec='seconds')}'"
            f")>"
        )

    def entity_ids(self, point_in_time=None):
        """Return the entity ids that existed in this run.

        Specify point_in_time if you want to know which existed at that point
        in time inside the run.
        """
        session = Session.object_session(self)

        assert session is not None, "RecorderRuns need to be persisted"

        query = session.query(distinct(States.entity_id)).filter(
            States.last_updated >= self.start
        )

        if point_in_time is not None:
            query = query.filter(States.last_updated < point_in_time)
        elif self.end is not None:
            query = query.filter(States.last_updated < self.end)

        return [row[0] for row in query]

    def to_native(self, validate_entity_id=True):
        """Return self, native format is this model."""
        return self


class SchemaChanges(Base):  # type: ignore
    """Representation of schema version changes."""

    __tablename__ = TABLE_SCHEMA_CHANGES
    change_id = Column(Integer, Identity(), primary_key=True)
    schema_version = Column(Integer)
    changed = Column(DateTime(timezone=True), default=dt_util.utcnow)

    def __repr__(self) -> str:
        """Return string representation of instance for debugging."""
        return (
            f"<recorder.SchemaChanges("
            f"id={self.change_id}, schema_version={self.schema_version}, "
            f"changed='{self.changed.isoformat(sep=' ', timespec='seconds')}'"
            f")>"
        )


class StatisticsRuns(Base):  # type: ignore
    """Representation of statistics run."""

    __tablename__ = TABLE_STATISTICS_RUNS
    run_id = Column(Integer, Identity(), primary_key=True)
    start = Column(DateTime(timezone=True))

    def __repr__(self) -> str:
        """Return string representation of instance for debugging."""
        return (
            f"<recorder.StatisticsRuns("
            f"id={self.run_id}, start='{self.start.isoformat(sep=' ', timespec='seconds')}', "
            f")>"
        )


@overload
def process_timestamp(ts: None) -> None:
    ...


@overload
def process_timestamp(ts: datetime) -> datetime:
    ...


def process_timestamp(ts: datetime | None) -> datetime | None:
    """Process a timestamp into datetime object."""
    if ts is None:
        return None
    if ts.tzinfo is None:
        return ts.replace(tzinfo=dt_util.UTC)

    return dt_util.as_utc(ts)


@overload
def process_timestamp_to_utc_isoformat(ts: None) -> None:
    ...


@overload
def process_timestamp_to_utc_isoformat(ts: datetime) -> str:
    ...


def process_timestamp_to_utc_isoformat(ts: datetime | None) -> str | None:
    """Process a timestamp into UTC isotime."""
    if ts is None:
        return None
    if ts.tzinfo == dt_util.UTC:
        return ts.isoformat()
    if ts.tzinfo is None:
        return f"{ts.isoformat()}{DB_TIMEZONE}"
    return ts.astimezone(dt_util.UTC).isoformat()


class LazyState(State):
    """A lazy version of core State."""

    __slots__ = [
        "_row",
        "entity_id",
        "state",
        "_attributes",
        "_last_changed",
        "_last_updated",
        "_context",
    ]

    def __init__(self, row):  # pylint: disable=super-init-not-called
        """Init the lazy state."""
        self._row = row
        self.entity_id = self._row.entity_id
        self.state = self._row.state or ""
        self._attributes = None
        self._last_changed = None
        self._last_updated = None
        self._context = None

    @property  # type: ignore
    def attributes(self):
        """State attributes."""
        if not self._attributes:
            try:
                self._attributes = json.loads(self._row.attributes)
            except ValueError:
                # When json.loads fails
                _LOGGER.exception("Error converting row to state: %s", self._row)
                self._attributes = {}
        return self._attributes

    @attributes.setter
    def attributes(self, value):
        """Set attributes."""
        self._attributes = value

    @property  # type: ignore
    def context(self):
        """State context."""
        if not self._context:
            self._context = Context(id=None)
        return self._context

    @context.setter
    def context(self, value):
        """Set context."""
        self._context = value

    @property  # type: ignore
    def last_changed(self):
        """Last changed datetime."""
        if not self._last_changed:
            self._last_changed = process_timestamp(self._row.last_changed)
        return self._last_changed

    @last_changed.setter
    def last_changed(self, value):
        """Set last changed datetime."""
        self._last_changed = value

    @property  # type: ignore
    def last_updated(self):
        """Last updated datetime."""
        if not self._last_updated:
            self._last_updated = process_timestamp(self._row.last_updated)
        return self._last_updated

    @last_updated.setter
    def last_updated(self, value):
        """Set last updated datetime."""
        self._last_updated = value

    def as_dict(self):
        """Return a dict representation of the LazyState.

        Async friendly.

        To be used for JSON serialization.
        """
        if self._last_changed:
            last_changed_isoformat = self._last_changed.isoformat()
        else:
            last_changed_isoformat = process_timestamp_to_utc_isoformat(
                self._row.last_changed
            )
        if self._last_updated:
            last_updated_isoformat = self._last_updated.isoformat()
        else:
            last_updated_isoformat = process_timestamp_to_utc_isoformat(
                self._row.last_updated
            )
        return {
            "entity_id": self.entity_id,
            "state": self.state,
            "attributes": self._attributes or self.attributes,
            "last_changed": last_changed_isoformat,
            "last_updated": last_updated_isoformat,
        }

    def __eq__(self, other):
        """Return the comparison."""
        return (
            other.__class__ in [self.__class__, State]
            and self.entity_id == other.entity_id
            and self.state == other.state
            and self.attributes == other.attributes
        )
