import logging
from datetime import timedelta
from typing import Any
from urllib.parse import quote

from google.oauth2 import service_account
from googleapiclient.discovery import build

log = logging.getLogger(__name__)

class GCalendar:
    def __init__(self, config, state_store, google_secret):
        self.config = config
        self.state = state_store
        self._google = None
        self.google_secret = google_secret

    def google(self):
        if self._google is None:
            creds = service_account.Credentials.from_service_account_info(
                self.google_secret.data, scopes=["https://www.googleapis.com/auth/calendar"]
            )
            # cache_discovery=False avoids writing discovery cache files in odd environments
            self._google = build("calendar", "v3", credentials=creds, cache_discovery=False)
        return self._google

    def reset_google(self):
        self._google = None

    def _finish_calendar(self, cid: str) -> str:
        self.state.set("calendar_id", cid)
        
        admin = self.config.get("admin_email")
        acls = [{"scope_type": "default", "scope_value": None, "role": "reader"}]
        if admin:
            acls.append({"scope_type": "user", "scope_value": admin, "role": "writer"})
        self.sync_acls(acls)
        
        return cid

    def calendar_id(self) -> str:
        cached = self.state.get("calendar_id")
        if cached:
            return cached

        # Calendar not cached on disk; look up calendar by name
        name = self.config.get("calendar_name", "RunnerHub Job Postings")
        page_token = None
        matches = []

        while True:
            resp = self.google().calendarList().list(pageToken=page_token).execute()
            for cal in resp.get("items", []):
                if cal.get("summary") == name:
                    matches.append(cal)
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
            
        # Found calendar by name; let's verify its settings and save it to disk
        if len(matches) == 1:
            cid = matches[0]["id"]
            log.info("Using existing calendar id=%s", cid)
            self._finish_calendar(cid)
            return cid

        # Found more than one calendar with the same name! Currently the only solution is to enter the ID manually.
        if len(matches) > 1:
            raise RuntimeError(f"Multiple calendars named {name!r}. Disambiguate manually.")

        # Couldn't find a calendar, but we have everything we need, so let's make a new one!
        created = self.google().calendars().insert(
            body={"summary": name, "timeZone": self.config.get("timezone", "UTC")}
        ).execute()
        cid = created["id"]
        log.info("Created calendar id=%s", cid)
        self._finish_calendar(cid)
        return cid

    # The whole-calendar link
    def google_subscribe_link(self) -> str:
        cid = self.calendar_id()
        return "https://calendar.google.com/calendar/u/0/r?cid=" + quote(cid, safe="")


    # ===== ACCESS CONTROL =====
    @staticmethod
    def _scope_key(scope_type: str, scope_value: str | None) -> tuple[str, str | None]:
        return scope_type, scope_value

    def _rule_key(self, rule: dict) -> tuple[str, str | None]:
        scope = rule.get("scope") or {}
        return self._scope_key(scope.get("type", ""), scope.get("value"))

    def sync_acls(
        self,
        desired: list[dict[str, str | None]]
    ) -> None:
        """
        For each role in desired, set permission to exactly the given value.
        Logs permissions in google acl that aren't in the desired list.
        """
        cid = self.calendar_id()
        svc = self.google().acl()

        # Build desired map (last one wins if duplicates)
        desired_map: dict[tuple[str, str | None], dict[str, str | None]] = {}
        for d in desired:
            role = d.get("role")
            scope_type = d.get("scope_type")
            scope_value = d.get("scope_value")
            if not isinstance(scope_type, str) or not scope_type:
                raise ValueError(f"Bad desired scope_type: {scope_type!r}")
            if role not in {"reader": 1, "writer": 2, "owner": 3}:
                raise ValueError(f"Bad desired role: {role!r}")
            if scope_value is not None and not isinstance(scope_value, str):
                raise ValueError(f"Bad desired scope_value: {scope_value!r}")

            desired_map[self._scope_key(scope_type, scope_value)] = d

        # Track non-matching entries
        extras: list[dict] = []
        updates: list[tuple[str, dict]] = []  # (ruleId, updated_body)

        # One traversal over server ACLs
        page_token: str | None = None
        while True:
            resp = svc.list(calendarId=cid, pageToken=page_token).execute()
            for rule in resp.get("items", []):
                key = self._rule_key(rule)
                desired_rule = desired_map.pop(key, None)
                
                # Entry wasn't one of the desired ones; we'll log it later, possibly do more in the future
                if desired_rule is None:
                    extras.append(rule)
                    continue

                desired_role = desired_rule["role"]
                if rule.get("role") != desired_role:
                    updates.append((rule["id"], {**rule, "role": desired_role}))

            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        # Apply updates
        for rule_id, body in updates:
            svc.update(calendarId=cid, ruleId=rule_id, body=body).execute()

        # Insert missing desired rules
        for (scope_type, scope_value), d in desired_map.items():
            body = {"scope": {"type": scope_type}, "role": d["role"]}
            if scope_value is not None:
                body["scope"]["value"] = scope_value
            svc.insert(calendarId=cid, body=body).execute()

        # Log extras for visibility
        for rule in extras:
            scope = rule.get("scope") or {}
            log.info(
                "Unmanaged ACL: type=%s value=%s role=%s id=%s",
                scope.get("type"),
                scope.get("value"),
                rule.get("role"),
                rule.get("id"),
            )


    # ===== EVENT CREATION =====

    def _build_calendar_event(self, entry: Any) -> dict[str, Any]:
        start_dt = entry.parsed_time
        end_dt = start_dt + timedelta(minutes=self.config.get("event_duration_min", 240))
        return {
            "summary": getattr(entry, "title", ""),
            "description": f"Reddit thread: {getattr(entry, 'link', '')}",
            "start": {"dateTime": start_dt.isoformat(), "timeZone": self.config.get("timezone", "UTC")},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": self.config.get("timezone", "UTC")},
        }
    
    def put_event(self, entry, event_id: str | None = None):
        cid = self.calendar_id()
        body = self._build_calendar_event(entry)
        events = self.google().events()
        if event_id:
            event = events.update(calendarId=cid, body=body, eventId=event_id).execute()
            log.info("Updated event: %s", event.get("htmlLink"))
        else:
            event = events.insert(calendarId=cid, body=body).execute()
        log.info("Created event: %s", event.get("htmlLink"))
        return event
