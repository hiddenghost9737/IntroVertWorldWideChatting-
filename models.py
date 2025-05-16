from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
import uuid

db = SQLAlchemy()

def generate_uuid():
    return str(uuid.uuid4())

class User(db.Model, UserMixin):
    __tablename__ = 'users'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    display_name = db.Column(db.String(100))
    bio = db.Column(db.Text)
    avatar_url = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    status = db.relationship('UserStatus', backref='user', uselist=False, cascade='all, delete-orphan')
    sent_messages = db.relationship('Message', foreign_keys='Message.sender_id', backref='sender', lazy='dynamic', cascade='all, delete-orphan')
    received_messages = db.relationship('Message', foreign_keys='Message.receiver_id', backref='receiver', lazy='dynamic')
    followers = db.relationship('UserFollow', foreign_keys='UserFollow.following_id', backref='following', lazy='dynamic', cascade='all, delete-orphan')
    following = db.relationship('UserFollow', foreign_keys='UserFollow.follower_id', backref='follower', lazy='dynamic', cascade='all, delete-orphan')
    reactions = db.relationship('MessageReaction', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    notifications = db.relationship('Notification', backref='user', lazy='dynamic', cascade='all, delete-orphan')

class UserStatus(db.Model):
    __tablename__ = 'user_status'
    
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), primary_key=True)
    is_online = db.Column(db.Boolean, default=False)
    last_active = db.Column(db.DateTime, default=datetime.utcnow)

class Message(db.Model):
    __tablename__ = 'messages'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    sender_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=True)
    receiver_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=True)
    content = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    reactions = db.relationship('MessageReaction', backref='message', lazy='dynamic', cascade='all, delete-orphan')
    related_notifications = db.relationship('Notification', backref='related_message', lazy='dynamic')

class UserFollow(db.Model):
    __tablename__ = 'user_follows'
    
    follower_id = db.Column(db.String(36), db.ForeignKey('users.id'), primary_key=True)
    following_id = db.Column(db.String(36), db.ForeignKey('users.id'), primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class MessageReaction(db.Model):
    __tablename__ = 'message_reactions'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    message_id = db.Column(db.String(36), db.ForeignKey('messages.id'), nullable=False)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    emoji = db.Column(db.String(10), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('message_id', 'user_id', 'emoji', name='unique_reaction'),
    )

class Notification(db.Model):
    __tablename__ = 'notifications'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    content = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    related_user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=True)
    related_message_id = db.Column(db.String(36), db.ForeignKey('messages.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    related_user = db.relationship('User', foreign_keys=[related_user_id])
