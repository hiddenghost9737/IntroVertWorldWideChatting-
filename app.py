from flask import Flask, render_template, redirect, url_for, flash, request, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import os
from dotenv import load_dotenv

from models import db, User, UserStatus, Message, UserFollow, MessageReaction, Notification
from forms import LoginForm, RegistrationForm, ProfileForm, MessageForm

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key-for-testing')

# Configure database
database_url = os.getenv('NEON_DATABASE_URL')
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///introvertchat.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static/uploads')

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize extensions
db.init_app(app)
with app.app_context():
    db.create_all()
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(user_id)

# Routes
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('chat'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('chat'))
    
    form = RegistrationForm()
    if form.validate_on_submit():
        # Check if user already exists
        existing_user = User.query.filter(
            (User.username == form.username.data) | (User.email == form.email.data)
        ).first()
        
        if existing_user:
            flash('Username or email already exists.', 'danger')
            return render_template('register.html', form=form)
        
        # Create new user
        hashed_password = generate_password_hash(form.password.data)
        new_user = User(
            username=form.username.data,
            email=form.email.data,
            password_hash=hashed_password,
            display_name=form.username.data
        )
        
        db.session.add(new_user)
        db.session.commit()
        
        # Create user status
        user_status = UserStatus(
            user_id=new_user.id,
            is_online=True,
            last_active=datetime.utcnow()
        )
        db.session.add(user_status)
        db.session.commit()
        
        # Log in the new user
        login_user(new_user)
        flash('Registration successful! Welcome to IntrovertChat.', 'success')
        return redirect(url_for('chat'))
    
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('chat'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        
        if user and check_password_hash(user.password_hash, form.password.data):
            login_user(user)
            
            # Update user status
            user_status = UserStatus.query.filter_by(user_id=user.id).first()
            if user_status:
                user_status.is_online = True
                user_status.last_active = datetime.utcnow()
            else:
                user_status = UserStatus(
                    user_id=user.id,
                    is_online=True,
                    last_active=datetime.utcnow()
                )
                db.session.add(user_status)
            
            db.session.commit()
            
            flash('Login successful!', 'success')
            return redirect(url_for('chat'))
        else:
            flash('Invalid email or password.', 'danger')
    
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    # Update user status
    user_status = UserStatus.query.filter_by(user_id=current_user.id).first()
    if user_status:
        user_status.is_online = False
        user_status.last_active = datetime.utcnow()
        db.session.commit()
    
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/chat')
@login_required
def chat():
    # Get recent chats
    recent_chats = db.session.query(
        User, Message.created_at.label('last_message_time')
    ).join(
        Message, 
        ((Message.sender_id == User.id) & (Message.receiver_id == current_user.id)) |
        ((Message.receiver_id == User.id) & (Message.sender_id == current_user.id))
    ).filter(
        User.id != current_user.id
    ).group_by(
        User.id
    ).order_by(
        Message.created_at.desc()
    ).all()
    
    # Get user statuses
    user_ids = [user.id for user, _ in recent_chats]
    statuses = UserStatus.query.filter(UserStatus.user_id.in_(user_ids)).all() if user_ids else []
    status_dict = {status.user_id: status for status in statuses}
    
    return render_template('chat.html', recent_chats=recent_chats, status_dict=status_dict)

@app.route('/chat/<user_id>')
@login_required
def chat_with_user(user_id):
    other_user = User.query.get_or_404(user_id)
    
    # Get messages between current user and other user
    messages = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.receiver_id == other_user.id)) |
        ((Message.sender_id == other_user.id) & (Message.receiver_id == current_user.id))
    ).order_by(Message.created_at).all()
    
    # Mark messages as read
    unread_messages = [m for m in messages if m.sender_id == other_user.id and not m.is_read]
    for message in unread_messages:
        message.is_read = True
    
    if unread_messages:
        db.session.commit()
    
    # Get user status
    user_status = UserStatus.query.filter_by(user_id=other_user.id).first()
    
    form = MessageForm()
    
    return render_template(
        'chat_messages.html', 
        other_user=other_user, 
        messages=messages, 
        form=form,
        user_status=user_status
    )

@app.route('/search', methods=['GET', 'POST'])
@login_required
def search_users():
    if request.method == 'POST':
        search_query = request.form.get('search_query', '')
        if search_query:
            users = User.query.filter(
                User.id != current_user.id,
                (User.username.ilike(f'%{search_query}%') | User.display_name.ilike(f'%{search_query}%'))
            ).limit(10).all()
            
            # Get user statuses
            user_ids = [user.id for user in users]
            statuses = UserStatus.query.filter(UserStatus.user_id.in_(user_ids)).all() if user_ids else []
            status_dict = {status.user_id: status for status in statuses}
            
            return render_template('search_results.html', users=users, status_dict=status_dict)
    
    return redirect(url_for('chat'))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    form = ProfileForm(obj=current_user)
    
    if form.validate_on_submit():
        current_user.display_name = form.display_name.data
        current_user.bio = form.bio.data
        
        if form.avatar.data:
            filename = secure_filename(f"{current_user.id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            form.avatar.data.save(filepath)
            current_user.avatar_url = f"/static/uploads/{filename}"
        
        db.session.commit()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('profile'))
    
    return render_template('profile.html', form=form)

# API routes
@app.route('/api/send_message', methods=['POST'])
@login_required
def send_message():
    receiver_id = request.form.get('receiver_id')
    content = request.form.get('content')
    
    if not receiver_id or not content:
        return jsonify({'success': False, 'error': 'Missing required fields'}), 400
    
    # Create new message
    message = Message(
        sender_id=current_user.id,
        receiver_id=receiver_id,
        content=content,
        is_read=False,
        created_at=datetime.utcnow()
    )
    
    db.session.add(message)
    db.session.commit()
    
    # Emit socket event
    socketio.emit('new_message', {
        'id': message.id,
        'sender_id': message.sender_id,
        'receiver_id': message.receiver_id,
        'content': message.content,
        'is_read': message.is_read,
        'created_at': message.created_at.isoformat(),
        'sender': {
            'id': current_user.id,
            'username': current_user.username,
            'display_name': current_user.display_name,
            'avatar_url': current_user.avatar_url
        }
    }, room=f"user_{receiver_id}")
    
    return jsonify({
        'success': True,
        'message': {
            'id': message.id,
            'sender_id': message.sender_id,
            'receiver_id': message.receiver_id,
            'content': message.content,
            'is_read': message.is_read,
            'created_at': message.created_at.isoformat()
        }
    })

@app.route('/api/mark_read', methods=['POST'])
@login_required
def mark_read():
    message_id = request.form.get('message_id')
    
    if not message_id:
        return jsonify({'success': False, 'error': 'Missing message ID'}), 400
    
    message = Message.query.get(message_id)
    
    if not message or message.receiver_id != current_user.id:
        return jsonify({'success': False, 'error': 'Message not found or unauthorized'}), 404
    
    message.is_read = True
    db.session.commit()
    
    return jsonify({'success': True})

# Health check endpoint for Render
@app.route('/health')
def health_check():
    return jsonify({'status': 'ok'}), 200

# Socket.IO events
@socketio.on('connect')
def handle_connect():
    if current_user.is_authenticated:
        join_room(f"user_{current_user.id}")
        
        # Update user status
        user_status = UserStatus.query.filter_by(user_id=current_user.id).first()
        if user_status:
            user_status.is_online = True
            user_status.last_active = datetime.utcnow()
            db.session.commit()
            
            # Broadcast status change to all users
            socketio.emit('status_change', {
                'user_id': current_user.id,
                'is_online': True,
                'last_active': user_status.last_active.isoformat()
            }, broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    if current_user.is_authenticated:
        leave_room(f"user_{current_user.id}")
        
        # Update user status
        user_status = UserStatus.query.filter_by(user_id=current_user.id).first()
        if user_status:
            user_status.is_online = False
            user_status.last_active = datetime.utcnow()
            db.session.commit()
            
            # Broadcast status change to all users
            socketio.emit('status_change', {
                'user_id': current_user.id,
                'is_online': False,
                'last_active': user_status.last_active.isoformat()
            }, broadcast=True)

# Add current year to all templates
@app.context_processor
def inject_now():
    return {'now': datetime.utcnow()}

if __name__ == '__main__':
    # Use this for development
    # socketio.run(app, debug=True)
    
    # Use this for production
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host='0.0.0.0', port=port)
