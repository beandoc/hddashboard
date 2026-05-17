def to_dict(obj):
    """Serialize SQLAlchemy model to dictionary, skipping internal state and relationships."""
    if not obj:
        return None
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}
