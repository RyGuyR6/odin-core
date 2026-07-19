"""Persistent authentication repository."""

from __future__ import annotations

from app.auth.models import ApiKeyRecord, UserRecord
from app.storage.service import storage_service


class AuthRepository:
    users_namespace = "auth_users"
    usernames_namespace = "auth_usernames"
    emails_namespace = "auth_emails"
    api_keys_namespace = "auth_api_keys"
    api_key_prefix_namespace = "auth_api_key_prefixes"

    @property
    def backend(self):
        return storage_service.backend

    def save_user(self, user: UserRecord) -> UserRecord:
        existing = self.get_user(user.id)
        if existing and existing.username != user.username:
            self.backend.delete_record(self.usernames_namespace, existing.username)
        if existing and existing.email and existing.email != user.email:
            self.backend.delete_record(self.emails_namespace, existing.email)

        self.backend.put_record(self.users_namespace, user.id, user.model_dump(mode="json"))
        self.backend.put_record(self.usernames_namespace, user.username, {"user_id": user.id})
        if user.email:
            self.backend.put_record(self.emails_namespace, user.email, {"user_id": user.id})
        return user

    def get_user(self, user_id: str) -> UserRecord | None:
        record = self.backend.get_record(self.users_namespace, user_id)
        return UserRecord.model_validate(record.payload) if record else None

    def get_user_by_username(self, username: str) -> UserRecord | None:
        index = self.backend.get_record(self.usernames_namespace, username.strip().lower())
        return self.get_user(index.payload["user_id"]) if index else None

    def get_user_by_email(self, email: str) -> UserRecord | None:
        index = self.backend.get_record(self.emails_namespace, email.strip().lower())
        return self.get_user(index.payload["user_id"]) if index else None

    def list_users(self, limit: int = 500, offset: int = 0) -> list[UserRecord]:
        return [
            UserRecord.model_validate(record.payload)
            for record in self.backend.list_records(
                self.users_namespace,
                limit=limit,
                offset=offset,
            )
        ]

    def count_users(self) -> int:
        return self.backend.count_records(self.users_namespace)

    def save_api_key(self, record: ApiKeyRecord) -> ApiKeyRecord:
        self.backend.put_record(
            self.api_keys_namespace,
            record.id,
            record.model_dump(mode="json"),
        )
        self.backend.put_record(
            self.api_key_prefix_namespace,
            record.key_prefix,
            {"api_key_id": record.id},
        )
        return record

    def get_api_key(self, key_id: str) -> ApiKeyRecord | None:
        record = self.backend.get_record(self.api_keys_namespace, key_id)
        return ApiKeyRecord.model_validate(record.payload) if record else None

    def get_api_key_by_prefix(self, prefix: str) -> ApiKeyRecord | None:
        index = self.backend.get_record(self.api_key_prefix_namespace, prefix)
        return self.get_api_key(index.payload["api_key_id"]) if index else None

    def list_api_keys(self, user_id: str) -> list[ApiKeyRecord]:
        records = self.backend.list_records(self.api_keys_namespace, limit=1000, offset=0)
        return [
            ApiKeyRecord.model_validate(record.payload)
            for record in records
            if record.payload.get("user_id") == user_id
        ]

    def delete_api_key(self, key_id: str) -> bool:
        record = self.get_api_key(key_id)
        if record is None:
            return False
        self.backend.delete_record(self.api_key_prefix_namespace, record.key_prefix)
        return self.backend.delete_record(self.api_keys_namespace, key_id)
