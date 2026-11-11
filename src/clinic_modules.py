"""The one clinic-module key this service still knows about on its own (spec 009).

The catalog of clinic modules belongs entirely to the users API, not to this service
(Principle IX): this service has no fixed list of module keys and validates no dependency between
them (that rule was retired, spec 009). `patients` is the only exception, because it MUST always
be included in every subscription regardless of what the request asks for (FR-017 of spec
004-correct-subscriptions-api, unchanged) — a guarantee this service makes on its own, not one the
users API enforces for it.
"""

PATIENTS_KEY = "patients"
