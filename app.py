#STANDARD LIBRARIES
import os
import io
import uuid
import sqlite3

#FLASK
from flask import Flask, render_template, request, redirect, send_file, session, send_from_directory, flash, jsonify, url_for
from flask_socketio import SocketIO, emit

#SECURITY
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

#CRYPTOGRAPHY
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import serialization, hashes

# 🔐 Generate RSA keys in memory (NO FILES)
private_key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048
)

public_key = private_key.public_key()
 
#GLOBAL VARIABLES
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-key")

socketio = SocketIO(app, cors_allowed_origins="*")

user_sid_map={}
pending_files = {}

connections = set()

UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'mkv'}

#HELPER FUNCTION
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

#HOMEPAGE
@app.route('/')
def home():
    return render_template('index.html')

#ABOUT
@app.route('/about')
def about():
    return "This is about page"

#REGISTER
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method=='POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        
        hashed_password = generate_password_hash(password)
        
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        
        # 🔍 Check if user already exists
        cursor.execute("SELECT * FROM users WHERE username=? OR email=?", (username, email))
        existing_user = cursor.fetchone()

        if existing_user:
            conn.close()
            flash("User already exists! Try different username/email.", "danger")
            return redirect('/')
        
        
        cursor.execute("INSERT INTO users(username,password,email) values (?, ?, ?)", (username, hashed_password, email))
        
        
        conn.commit()
        conn.close()
        
        flash("Registration successful! You can now login.", "success")
        return redirect('/') 
    
    return render_template('register.html')

#LOGIN
@app.route('/login', methods=['GET', 'POST'])
def login():
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        
        conn = sqlite3.connect('database.db')
        cursor=conn.cursor()
        
        cursor.execute("SELECT * FROM users WHERE username=? AND email = ?", (username, email))
        user = cursor.fetchone()
        
        print(user)
        
        conn.close()
        
        if user and check_password_hash(user[2], password):
            session['username'] = username
            
            flash("Login successful!", "success")
            return redirect('/')
        else:
            flash("Invalid credentials", "danger")
            return redirect('/login')
    
    return render_template('login.html')

#LOGOUT
@app.route('/logout')
def logout():
    session.pop('username', None)
    flash("Logged out successfully", "info")
    return redirect('/')

#DASHBOARD
@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'username' not in session:
        flash("Please login first", "warning")
        return redirect('/login')
    
    if request.method == 'POST':
        file = request.files['file']
        
        if file and file.filename != '' and allowed_file(file.filename):
            filename = str(uuid.uuid4()) + "_" + secure_filename(file.filename or "")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            
            #read file
            file_data = file.read()
            
            #generate unique key per file
            aes_key=Fernet.generate_key()
            cipher = Fernet(aes_key)
            
            #encypt data
            encrypted_data = cipher.encrypt(file_data)
            
            #save encypted file
            with open(filepath, 'wb') as f:
                f.write(encrypted_data)
                
                
            #ENCYPT AES KEY USING RSA
            encrypted_key = public_key.encrypt(
                aes_key,
                padding.OAEP(
                    mgf = padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            ) 
            
            #save to DB
            conn=sqlite3.connect('database.db')
            c = conn.cursor()
            
            c.execute("INSERT INTO files (filename, username, file_key) VALUES (?, ?, ?)",
                      (filename, session['username'], encrypted_key.hex()))
            
            conn.commit()
            conn.close()
            
            
            flash(f"File '{file.filename}' uploaded successfully!", "success")
            return redirect(url_for('dashboard'))
        else:
            flash("File extension not allowed!", "danger")
            return redirect(url_for('dashboard'))
    
    #Fetch user's files
    conn=sqlite3.connect('database.db')
    c = conn.cursor()
    
    c.execute("SELECT id, filename FROM files WHERE username=?", (session['username'],))
    files=c.fetchall()
    
    # Files shared with current user
    c.execute("""
    SELECT files.id, files.filename 
    FROM files 
    JOIN shared_files 
    ON files.id = shared_files.file_id 
    WHERE shared_files.shared_with=?
    """, (session['username'],))

    shared_files = c.fetchall()    
    conn.close()
    
    return render_template('dashboard.html', files=files, shared_files=shared_files)


#PROFILE
@app.route('/profile')
def profile():
    if 'username' not in session:
        return redirect('/login')
    
    return render_template('profile.html')




#DOWNLOAD
@app.route('/download/<int:file_id>')
def download(file_id):
    if 'username' not in session:
        return "Login required"
    
    conn=sqlite3.connect('database.db')
    c=conn.cursor()
    
    c.execute("SELECT filename, username, file_key FROM files WHERE id=?", (file_id,))
    
    file=c.fetchone()
    #conn.close()
    
    if file:

        filename, owner, key = file

        
        # Check if shared
        c.execute("SELECT * FROM shared_files WHERE file_id=? AND shared_with=?", 
                (file_id, session['username']))
        shared = c.fetchone()
        conn.close()
        
        
        if owner == session['username'] or shared:
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            
            #read encyrpted file
            with open(filepath, 'rb') as f:
                encrypted_data = f.read()
            
            """"
            #decrypt
            cipher=Fernet(key.encode())
            decrypted_data = cipher.decrypt(encrypted_data)
            """
            

            # convert stored key back to bytes
            encrypted_key = bytes.fromhex(key)

            # decrypt AES key
            aes_key = private_key.decrypt(
                encrypted_key,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            )

            # decrypt file
            cipher = Fernet(aes_key)
            decrypted_data = cipher.decrypt(encrypted_data)
            
            #send file(important: using memory)
            return send_file(
                io.BytesIO(decrypted_data),
                as_attachment=True,
                download_name=filename
            )
                       
        else:
            return "Unauthorized access"
    return "File not found"

#DELETE FILES
@app.route('/delete/<int:file_id>')
def delete_file(file_id):
    if 'username' not in session:
        return "Please Login First"
    
    conn=sqlite3.connect('database.db')
    c=conn.cursor()
    
    #get file info
    c.execute("SELECT filename, username FROM files where id = ?",(file_id,))
    file=c.fetchone()
    
    if file:
        filename, owner = file
        
        #check ownership
        if owner == session['username']:
            filepath=os.path.join(app.config['UPLOAD_FOLDER'], filename)
            
            if os.path.exists(filepath):
                os.remove(filepath)
            
            c.execute("DELETE FROM files WHERE id = ?",(file_id,))
            conn.commit()
            conn.close()
    return redirect('/dashboard')

#SHARE FILE
@app.route('/share/<int:file_id>', methods=['POST'])
def share(file_id):
    if 'username' not in session:
        return "Login required"
    
    shared_user = request.form['username']
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    #check ownership
    c.execute("SELECT username FROM files WHERE id=?", (file_id,))
    owner = c.fetchone()
    
    if owner and owner[0] == session['username']:
        
        # check if user exists
        c.execute("SELECT * FROM users WHERE username=?", (shared_user,))
        user_exists = c.fetchone()

        if not user_exists:
            return "User does not exist"
        
        c.execute("INSERT INTO shared_files (file_id, shared_with) VALUES (?, ?)",
        (file_id, shared_user))
                 
        conn.commit()
        conn.close()
    return redirect('/dashboard')

#CONNECT
@socketio.on('connect')
def handle_connect():
    sid = request.sid
    username = session.get('username')
    
    if not username:
        return
    
    user_sid_map[username] = sid
    
    
    print(f"{username} connected with SID {sid}")
    print("Online Users", list(user_sid_map.keys()))
    socketio.emit('update_users', list(user_sid_map.keys()))
    emit('update_users', list(user_sid_map.keys()))
    
    user_connections = []

    for (u1, u2) in connections:
        if u1 == username:
            user_connections.append(u2)

    emit('restore_connections', user_connections)

    
#DISCONNECT
@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    
    username_to_remove = None
    
    for username, stored_sid in user_sid_map.items():
            if stored_sid == sid:
                username_to_remove = username
                break

    if username_to_remove:
        del user_sid_map[username_to_remove]
        print(f"{username_to_remove} disconnected")

    socketio.emit('update_users', list(user_sid_map.keys()))

 
#SEND REQUEST
@socketio.on('send_request')
def handle_send_request(data):
    sender_username = session.get('username')
    receiver_username = data['to']

    receiver_sid = user_sid_map.get(receiver_username)
    
    if not receiver_sid:
        return
    #print(f"REQUEST RECEIVED: {sender_username} → {receiver_username}")

    # send request to receiver
    emit('receive_request', {
        'from': sender_username
    }, to=receiver_sid)
    
#ACCEPT_REQUEST   
@socketio.on('accept_request')
def handle_accept(data):
    receiver_username = session.get('username')
    sender_username = data['to']

    sender_sid = user_sid_map.get(sender_username)
    receiver_sid = user_sid_map.get(receiver_username)

    connections.add((sender_username, receiver_username))
    connections.add((receiver_username, sender_username))   

    emit('request_accepted', {
        'from': receiver_username,
        'type': 'sender'
    }, to=sender_sid)

    emit('request_accepted', {
        'from': sender_username,
        'type': 'receiver'
    }, to=receiver_sid)

#REJECT REQUEST
@socketio.on('reject_request')
def handle_reject(data):
    receiver_id = request.sid
    sender_id = data['to']
    sender_sid = user_sid_map.get(sender_id)

    if sender_sid:
        emit('request_rejected', {}, to=sender_sid)
        
    print(f"{receiver_id} rejected request from {sender_id}")
 
#FILE-SEND REQUEST
@socketio.on('file_send_request')
def handle_file_request(data):
    sender_username = session.get('username')
    file_name = data['fileName']
    receiver_username = data['to']
    
    receiver_sid = user_sid_map.get(receiver_username)
    if not receiver_sid:
        return

    pending_files[sender_username] = {
        "fileName": file_name,
        "to": receiver_username
    }
    
    emit('incoming_file', {
        'from': sender_username,
        'fileName': file_name,
        'totalSize': data.get('totalSize') 
    }, to=receiver_sid)  

#FILE-DATA
@socketio.on('file_data')
def handle_file_data(data):
    sender_username = session.get('username')
    receiver_username = data['to']
    
    receiver_sid = user_sid_map.get(receiver_username)
    
    if not receiver_sid:
        return
    
    emit('receive_file', data, to=receiver_sid)

#FILE ACCEPT
@socketio.on('file_accept')
def handle_file_accept(data):
    receiver_username = session.get('username')
    sender_username = data['to']
    
    sender_sid = user_sid_map.get(sender_username)

    #print(f"{receiver_id} accepted file from {sender_id}")

    emit('start_file_transfer', pending_files[sender_username], to=sender_sid)
    del pending_files[sender_username]


#FILE CHUNK
@socketio.on('file_chunk')
def handle_chunk(data):

    receiver_username = data['to']
    receiver_sid = user_sid_map.get(receiver_username)

    if not receiver_sid:
        return

    # 🔥 ONLY update when LAST chunk comes
    if data.get("isLast") and not data.get("counted"):

        sender = session.get("username")
        receiver = receiver_username
        filename = data.get("fileName")

        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()

        cursor.execute("UPDATE users SET sent = sent + 1 WHERE username=?", (sender,))
        cursor.execute("UPDATE users SET received = received + 1 WHERE username=?", (receiver,))
        
        cursor.execute("""
            INSERT INTO transfers (sender, receiver, filename)
            VALUES (?, ?, ?)
        """, (sender, receiver, filename))
        
        conn.commit()
        conn.close()

    # send chunk normally
    emit('receive_chunk', data, to=receiver_sid)
    
#ACK_CHUNK
@socketio.on('ack_chunk')
def handle_ack(data):
    sender_username = data['to']
    sender_sid = user_sid_map.get(sender_username)

    if not sender_sid:
        return

    emit('next_chunk', {}, to=sender_sid)
    
@socketio.on('cancel_transfer')
def handle_cancel(data):
    to_user = data.get("to")

    if to_user in user_sid_map:
        socketio.emit('transfer_cancelled', room=user_sid_map[to_user])


@socketio.on('disconnect_user')
def handle_disconnect_user(data):
        from_user = session.get('username')
        to_user = data.get('to')

        if not from_user or not to_user:
            return

        # 🔥 REMOVE BOTH DIRECTIONS
        if (from_user, to_user) in connections:
            connections.remove((from_user, to_user))

        if (to_user, from_user) in connections:
            connections.remove((to_user, from_user))

        print(f"{from_user} disconnected from {to_user}")

        # 🔥 NOTIFY BOTH USERS
        from_sid = user_sid_map.get(from_user)
        to_sid = user_sid_map.get(to_user)

        if from_sid:
            emit('user_disconnected', {'user': to_user}, to=from_sid)

        if to_sid:
            emit('user_disconnected', {'user': from_user}, to=to_sid)
            
            


@app.route("/profile-data")
def profile_data():
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    username = session.get("username")

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    cursor.execute("SELECT username, email, sent, received FROM users WHERE username=?", (username,))
    user = cursor.fetchone()

    conn.close()

    if user:
        return jsonify({
            "username": user[0],
            "email": user[1],
            "sent": user[2],
            "received": user[3],
            "lastActive": "Just now"
        })

    return jsonify({"error": "User not found"}), 404

@app.route("/recent-transfers")
def recent_transfers():
    if "username" not in session:
        return jsonify([]), 401

    username = session.get("username")

    # ✅ get pagination params from request
    try:
        start = int(request.args.get("start", 0))
        limit = int(request.args.get("limit", 5))
    except ValueError:
        return jsonify({"error": "Invalid parameters"}), 400

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    cursor.execute("""
        SELECT sender, receiver, filename, timestamp
        FROM transfers
        WHERE sender=? OR receiver=?
        ORDER BY id DESC
        LIMIT ? OFFSET ?
    """, (username, username, limit, start))

    rows = cursor.fetchall()
    conn.close()

    result = []
    for r in rows:
        result.append({
            "sender": r[0],
            "receiver": r[1],
            "filename": r[2],
            "time": r[3] if len(r) > 3 else None
        })

    return jsonify(result)

@app.route("/update-profile", methods=["POST"])
def update_profile():
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()

    new_username = data.get("username")
    current_password = data.get("currentPassword")
    new_password = data.get("newPassword")

    username = session.get("username")

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    cursor.execute("SELECT password FROM users WHERE username=?", (username,))
    user = cursor.fetchone()

    if not user:
        return jsonify({"error": "User not found"}), 404

    # 🔐 VALIDATION
    if new_username and len(new_username) < 3:
        return jsonify({"error": "Username too short"}), 400

    if new_password and len(new_password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    # 🔄 UPDATE USERNAME EVERYWHERE
    if new_username and new_username != username:
        cursor.execute("SELECT * FROM users WHERE username=?", (new_username,))
        if cursor.fetchone():
            return jsonify({"error": "Username already taken"}), 400

        cursor.execute("UPDATE users SET username=? WHERE username=?", (new_username, username))
        cursor.execute("UPDATE files SET username=? WHERE username=?", (new_username, username))
        cursor.execute("UPDATE transfers SET sender=? WHERE sender=?", (new_username, username))
        cursor.execute("UPDATE transfers SET receiver=? WHERE receiver=?", (new_username, username))
        cursor.execute("UPDATE shared_files SET shared_with=? WHERE shared_with=?", (new_username, username))

        session["username"] = new_username

    # 🔄 UPDATE PASSWORD
    if new_password:
        if not current_password:
            return jsonify({"error": "Enter current password"}), 400

        if not check_password_hash(user[0], current_password):
            return jsonify({"error": "Wrong current password"}), 400

        hashed = generate_password_hash(new_password)
        cursor.execute("UPDATE users SET password=? WHERE username=?", (hashed, session["username"]))

    conn.commit()
    conn.close()

    return jsonify({"success": True})

          
#DATABASE  
def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    cursor.execute('''
                   
            CREATE TABLE IF NOT EXISTS users(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                password TEXT,
                email TEXT
            )
            
        ''')
    
    cursor.execute('''
                   
            CREATE TABLE IF NOT EXISTS files(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                username TEXT NOT NULL
            )
        ''')
            
    cursor.execute('''
                   
            CREATE TABLE IF NOT EXISTS shared_files(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER,
                shared_with TEXT NOT NULL
            )    
            
        ''')
    
    #cursor.execute('''
                #ALTER TABLE files ADD COLUMN file_key TEXT;  
       # ''')
       
    cursor.execute('''
            CREATE TABLE IF NOT EXISTS transfers(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender TEXT,
                receiver TEXT,
                filename TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
    ''')
       
    # try:
    #     cursor.execute("ALTER TABLE users ADD COLUMN sent INTEGER DEFAULT 0")
    # except:
    #     pass

    # try:
    #     cursor.execute("ALTER TABLE users ADD COLUMN received INTEGER DEFAULT 0")
    # except:
    #     pass
      

    conn.commit()
    conn.close()

init_db()

if __name__ == '__main__':
    init_db()
    socketio.run(app, host="0.0.0.0", port=5000)
    
