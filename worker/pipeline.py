
from apps.api.db import get_record, put_record, transaction

ORDER = {"drafted": 0, "submitted": 1, "viewed": 2, "replied": 3,
         "interview": 4, "hired": 5, "lost": 5}


def apply_events(tenant, events):
    with transaction() as db:
        for event in events:
            if get_record(db, tenant, "seen_event", event["id"]):
                continue
            status, subject = event["status"], event["subject"]
            if status not in ORDER:
                continue
            prior = get_record(db, tenant, "pipeline", subject)
            if not prior or (prior.value["status"] not in ("hired", "lost") and
                             ORDER[status] >= ORDER[prior.value["status"]]):
                put_record(db, tenant, "pipeline", subject, {"subject": subject, "status": status,
                           "event_id": event["id"], "synthetic": event.get("synthetic", False)})
            put_record(db, tenant, "seen_event", event["id"], {"processed": True})
