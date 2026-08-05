"""Broker adapters (ADR-0004). Only tradeos.execution may call submit_order."""

from tradeos.brokers.base import (
    BrokerAdapter,
    BrokerCapability,
    BrokerCapabilityError,
    BrokerProtocolError,
    assert_submittable,
)
from tradeos.brokers.fake import FakeBroker
from tradeos.brokers.paper import PaperBroker

__all__ = [
    "BrokerAdapter",
    "BrokerCapability",
    "BrokerCapabilityError",
    "BrokerProtocolError",
    "FakeBroker",
    "PaperBroker",
    "assert_submittable",
]
