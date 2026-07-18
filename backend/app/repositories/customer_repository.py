from sqlalchemy.orm import Session

from app.models.customer import Customer


class CustomerRepository:

    def __init__(self, db: Session):
        self.db = db

    def get(self, entity_id: int):
        return self.db.get(Customer, entity_id)

    def list(self):
        return self.db.query(Customer).all()

    def create(self, entity: Customer):
        self.db.add(entity)
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def delete(self, entity_id: int):
        entity = self.get(entity_id)
        if entity is None:
            return False

        self.db.delete(entity)
        self.db.commit()
        return True
