
from flask import Flask, Response,render_template, request, redirect, url_for, session, flash ,jsonify
import base64
import atexit
import cv2
from detection_service_che import CameraDetectionService

import numpy as np
from datetime import datetime 
import time
import json
import os
import subprocess
from werkzeug.security import check_password_hash, generate_password_hash



app = Flask(__name__)
app.secret_key = 'your_secret_key'


# Initialize detection service
detection_service = CameraDetectionService()





# Routes
#INICIO DE SESION
@app.route('/', methods=['GET', 'POST'])
def login():
    error = None  # Initialize error variable
    session.pop('username', None)
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        try:
            with open('users.json', 'r') as file:
                users = json.load(file)
        
            if username in users and check_password_hash(users[username]['password'], password):
                session['username'] = username

                session['role']= users[username]['role']
                return redirect(url_for('dashboard'))
        except FileNotFoundError:
            userList = {}
            error = 'Contraseña o usuario incorrecto'
        except json.JSONDecodeError:
            userList = {}
            error = 'Contraseña o usuario incorrecto'
        else:
            error = 'Contraseña o usuario incorrecto'  # Set error message

    return render_template('login.html', error=error)

#REGISTRO DE USUARIO
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        if password == confirm_password:
            hashed_password = generate_password_hash(password)

            with open('users.json', 'r') as file:
                users = json.load(file)

            users[username] = {'password': hashed_password}

            with open('users.json', 'w') as file:
                json.dump(users, file)

            return render_template('signup_success.html', username=username)

        else:
            return render_template('signup.html', error='Passwords do not match')

    return render_template('signup.html')

#MENU INICIAL
@app.route('/dashboard')
def dashboard():
    if 'username' in session:
        return render_template('dashboard.html', username=session['username'], role = session['role'])
    else:
        return redirect(url_for('login'))

#CERRAR SESSION
@app.route('/logout', methods=['GET', 'POST'])
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

#AGREGAR CAMARAS-----------------------
@app.route('/camera_opt')
def camera_opt():
    if 'username' in session:
        #-----
        #, role = session['role']
        # GET request shows the camera management page
        cameras = detection_service.get_all_cameras()
        return render_template('camera_management.html', username=session['username'], cameras=cameras)
            
    else:
        return redirect(url_for('login'))
    
@app.route('/start_camera/<camera_id>', methods=['POST'])
def start_camera(camera_id):
    if 'username' not in session:
        return jsonify({'success': False})
        
    success = detection_service.start_camera(camera_id)
    return jsonify({'success': success})

#[PROBAR FUNCIONAMIENTO]
@app.route('/add_camera', methods=['GET', 'POST'])
def add_camera():
    if 'username' not in session:
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        camera_url = request.form['camera_url']
        success, result = detection_service.add_camera(camera_url)
        
        if success:
            flash('Camera added successfully')
            return redirect(url_for('camera_opt'))
        else:
            flash(f'Failed to add camera: {result}')
            return redirect(url_for('camera_opt'))
            
    return render_template('camera_management.html', 
                         username=session['username'],
                         cameras=detection_service.get_all_cameras())

@app.route('/stop_camera/<camera_id>', methods=['POST'])
def stop_camera(camera_id):
    if 'username' not in session:
        return jsonify({'success': False})
        
    success = detection_service.stop_camera(camera_id)
    return jsonify({'success': success})

@app.route('/delete_camera/<camera_id>', methods=['POST'])
def delete_camera(camera_id):
    if 'username' not in session:
        return jsonify({'success': False})
        
    success = detection_service.delete_camera(camera_id)
    return jsonify({'success': success})

#--------------------------------------------------
'''
@app.route('/edit_camera/<camera_id>', methods=['GET', 'POST'])
def edit_camera(camera_id):
    if 'username' not in session:
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        new_url = request.form['camera_url']
        try:
            with open('rstp.json', 'r') as file:
                camera_list = json.load(file)
            
            if camera_id in camera_list:
                # Stop the camera if it's running
                detection_service.stop_camera(camera_id)
                
                # Update the URL
                camera_list[camera_id]['url'] = new_url
                
                with open('rstp.json', 'w') as file:
                    json.dump(camera_list, file)
                    
                # Restart the camera with new URL
                detection_service.start_camera(camera_id)
                
                flash('Camera updated successfully')
            else:
                flash('Camera not found')
                
        except (FileNotFoundError, json.JSONDecodeError) as e:
            flash('Error updating camera')
            
        return redirect(url_for('manage_cameras'))
        
    # GET request - show edit form
    try:
        with open('rstp.json', 'r') as file:
            camera_list = json.load(file)
            if camera_id in camera_list:
                camera = {
                    'id': camera_id,
                    'url': camera_list[camera_id]['url']
                }
                return render_template('edit_camera.html', 
                                     username=session['username'],
                                     camera=camera)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
        
    flash('Camera not found')
    return redirect(url_for('manage_cameras'))
'''    
#VER CAMARAS (SOLO PAGINA)   
@app.route('/view_cameras')
def view_cameras():
    if 'username' in session:
        try:
            # Load RTSP camera URLs from json
            with open('rstp.json', 'r') as file:
                rstpList = json.load(file)
        except FileNotFoundError:
            rstpList = {}
        except json.JSONDecodeError:
            rstpList = {}
        cameras = [{"id": key, "url": value["url"]} for key, value in rstpList.items()]
        #print(f"{cameras}")
        return render_template('view_cameras.html', username=session['username'], cameras=cameras)
    else:
        return redirect(url_for('login'))

#BOTON AJUSTES DE USUARIOS
@app.route('/optionsUsers', methods = ['GET','POST'])
def optionsUsers():
    if 'username' in session:
        if session['role'] == 'superAdmin':
            try:
                # Load users  from json
                with open('users.json', 'r') as file:
                    userList = json.load(file)
            except FileNotFoundError:
                userList = {}
            except json.JSONDecodeError:
                userList = {}

            users = [{"id": key, "role": value["role"]} for key, value in userList.items()]
            known_faces = detection_service.face_recognizer.get_known_faces()
            return render_template('optionsUsers.html', username=session['username'], role = session['role'],userL = users,known_faces=known_faces)
        else:
            return render_template('dashboard.html',  username=session['username'], role = session['role'])
    else:
        return redirect(url_for('login'))  
"""
---save video---
@app.route('/stream_camera')
def stream_camera():
    camera_url = request.args.get('camera_url')

    # Set up the directory to save HLS segments (if not already set)
    hls_output_dir = '/path/to/hls/dir'
    if not os.path.exists(hls_output_dir):
        os.makedirs(hls_output_dir)

    # Use ffmpeg to stream the RTSP feed to HLS
    command = [
        'ffmpeg',
        '-i', camera_url,  # The RTSP stream URL
        '-c:v', 'libx264',
        '-f', 'hls',
        '-hls_time', '2',  # Duration of each segment
        '-hls_list_size', '10',  # Number of segments in the playlist
        '-hls_flags', 'delete_segments',  # Delete old segments
        os.path.join(hls_output_dir, 'index.m3u8')  # Output HLS playlist
    ]

    # Run the ffmpeg command
    subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # Serve the HLS stream
    return Response(
        open(os.path.join(hls_output_dir, 'index.m3u8')).read(),
        content_type='application/x-mpegURL'
    )
"""

#OBTENER VIDEO DE CAMARAS Y MANDAR A LA PAGINA

@app.route('/stream_camera')
def stream_camera():
    camera_url = request.args.get('camera_url')
    camera_id = None
    
    # Find camera_id from URL
    try:
        with open('rstp.json', 'r') as file:
            cameras = json.load(file)
            for cid, info in cameras.items():
                if info['url'] == camera_url:
                    camera_id = cid
                    break
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    print(f"se encontro id  {camera_id}")
    def generate_frames(rtsp_url):
        cap = cv2.VideoCapture(rtsp_url)
        print(f"URL set: {rtsp_url}")
        if not cap.isOpened():
            print("Error: Could not open video stream")
            return

        # Optimize capture settings
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        prev_time = time.time()
        fps_limit = 30  # Limit FPS to reduce CPU usage

        while True:
            # Control FPS
            
            ret, frame = cap.read()
            if camera_id:
                # Get detections for this camera
                detections = detection_service.get_detections(camera_id)

                # Draw detections on frame
                for detection in detections:
                    box = detection['box']
                    label = f"{detection['class']} {detection['confidence']:.2f}"

                    # Draw rectangle
                    cv2.rectangle(frame, (box[0], box[1]), (box[2], box[3]), (0, 255, 0), 2)

                    # Draw label with better visibility
                    label_size, baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
                    y = box[1] - baseline - 5
                    cv2.rectangle(frame, (box[0], y - label_size[1]), 
                                (box[0] + label_size[0], y + baseline), (0, 255, 0), cv2.FILLED)
                    cv2.putText(frame, label, (box[0], y),
                              cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)

            # Optimize frame size if needed
            frame = cv2.resize(frame, (0, 0), fx=0.8, fy=0.8)  # Reduce size by 20%

            # Encode with optimized parameters
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 75]  # Slightly reduce quality for better performance
            ret, buffer = cv2.imencode('.jpg', frame, encode_param)
            if not ret:
                print("Error: Could not encode frame")
                break

            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n\r\n')

        # Release the video stream
        cap.release()

    # Check if the camera stream is available
    cap = cv2.VideoCapture(camera_url)
    if not cap.isOpened():
        cap.release()  # Always release resources
        print("Error: Could not open video stream, serving placeholder image.")
        # Serve the placeholder image
        with open("static/no_video.jpg", "rb") as placeholder:
            return Response(placeholder.read(), mimetype='image/jpeg')

    cap.release()  # Release the resources after checking

    # If the stream is available, return the generator
    return Response(generate_frames(camera_url), mimetype='multipart/x-mixed-replace; boundary=frame')

#BORRAR USUARIO
@app.route('/delete/<string:id_data>', methods = ['GET'])
def delete(id_data):

    errors=None
    i=0
    if 'username' in session:
        if session['role'] == 'superAdmin':
    
            try:
            # Load users  from json
                with open('users.json', 'r') as file:
                    userList = json.load(file)
                    #contar usuarios con role superadmin
                    
                    for key, value in userList.items():
                        if value['role'] == 'superAdmin':
                            i=i+1
                            
            except FileNotFoundError:
                userList = {}
            except json.JSONDecodeError:
                userList = {}

            if not id_data in userList or (userList[id_data]["role"]=="superAdmin" and i <= 1):
                with open('users.json', 'w') as file:
                    json.dump(userList, file, indent=4)
                    users = [{"id": key, "role": value["role"]} for key, value in userList.items()]
                    errors = "NO se encontro el usuario"
                    if i==1:
                        errors = "Debe existir al menos un usuario con nivel: \"superAdmin\""
                    #flash("Usuario no encontrado")
                return render_template('optionsUsers.html',error= errors,username=session['username'], role = session['role'],userL = users)
                
                
            else:
                del userList[id_data]  # Delete the user
                
                # Save the updated user list back to the JSON file
                with open('users.json', 'w') as file:
                    json.dump(userList, file, indent=4)
                    users = [{"id": key, "role": value["role"]} for key, value in userList.items()]
                    flash("Usuario eliminado")
                    if detection_service.face_recognizer.remove_face(id_data):
                        print("se elimino rostro")
                    else:
                        print("No se pudo eliminar rostro")
                return render_template('optionsUsers.html', username=session['username'], role = session['role'],userL = users)
            
        else:
            return render_template('optionsUsers.html',  username=session['username'], role = session['role'])
    else:
        return redirect(url_for('login'))  

#CARGAR USUARIO DESDE INTERFAZ SUPERADMINISTRADOR
#agregar superadmin
@app.route('/insert', methods = ['POST'])
def insert():
 if 'username' in session:
    
    if request.method == 'POST':
        username = request.form['name']
        password = request.form['password']
        role = request.form['role']
        i=0
        errors=None
        if username != "":
            hashed_password = generate_password_hash(password)

            with open('users.json', 'r') as file:
                userList = json.load(file)
                i = len(userList)
                
            #validar usuarios repetidos
            if username in userList or i>=4:
                 with open('users.json', 'w') as file:
                    json.dump(userList, file, indent=4)
                    users = [{"id": key, "role": value["role"]} for key, value in userList.items()]
                    errors= 'Nombre de usuario repetido'
                    if i>=4:
                        errors= 'Maximo de usuarios alcanzado'
                #flash("Usuario no encontrado")
                    return render_template('optionsUsers.html',error=errors ,username=session['username'], role = session['role'],userL = users)
            else:   
                #proceder a cargar si no existe
                userList[username] = {'password': hashed_password, 'role':role}

            with open('users.json', 'w') as file:
                json.dump(userList, file)
                users = [{"id": key, "role": value["role"]} for key, value in userList.items()]
            flash("Usuario agregado..")
            return render_template('optionsUsers.html', username=session['username'], role = session['role'],userL = users)    
            

    return render_template('optionsUsers.html',username=session['username'],role = session['role'])
 else:
    return redirect(url_for('login'))  

@app.route('/update',methods=['POST','GET'])
def update():
    errors=""
    if session['role'] == 'superAdmin':
        try:
           with open('users.json', 'r') as file:
             userList = json.load(file)
             
        except (FileNotFoundError, json.JSONDecodeError):
             userList = {}

        if request.method == 'POST':
                id= request.form["idUpdate"]
                username = request.form['nameUpdate']
                password = request.form['passwordUpdate']
                role = request.form['roleUpdate']
                if id in userList:
                  
                    userList[username] = userList.pop(id)
                    id_update = username  
                    if password.strip():
                        hashed_password = generate_password_hash(password)
                        userList[id_update]['password'] = hashed_password  
                    
                    userList[id_update]['role'] = role
                    
                    with open('users.json', 'w') as file:
                        json.dump(userList, file, indent=4)
                        users = [{"id": key, "role": value["role"]} for key, value in userList.items()]
                    flash("Usuario actualizado correctamente.")
                    return render_template('optionsUsers.html',username=session['username'], role = session['role'],userL = users)
                else:   
                    errors="Usuario no encontrado"
                users = [{"id": key, "role": value["role"]} for key, value in userList.items()]
                return render_template('optionsUsers.html',error= errors,username=session['username'], role = session['role'],userL = users)
        else:
            with open('users.json', 'w') as file:
                json.dump(userList, file, indent=4)
                users = [{"id": key, "role": value["role"]} for key, value in userList.items()]
            return render_template('optionsUsers.html',error= errors,username=session['username'], role = session['role'],userL = users)
    else:
        return render_template('dashboard.html', username=session['username'], role = session['role'])
    



@app.route('/add_face', methods=['GET', 'POST'])
def add_face():
    if 'username' not in session:
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        name = request.form.get('name')
        
        if 'face_image' not in request.files:
            
            return 'No file uploaded', 400
            
        file = request.files['face_image']
        if file.filename == '':
            return 'No file selected', 400
            
        if file:
            # Leer la imagen
            img_stream = file.read()
            nparr = np.frombuffer(img_stream, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            # Detectar rostro
            faces = detection_service.face_detector.detect_faces(img)
            if not faces:
                return 'No face detected in image', 400
                
            # Tomar el primer rostro detectado
            face = faces[0]
            x, y, width, height = face['box']
            face_img = img[y:y+height, x:x+width]
            
            # Agregar a la base de datos
            if detection_service.face_recognizer.add_face(face_img, name):
                flash(f'Face added successfully for {name}')
            else:
                flash('Error adding face')
                
            return redirect(url_for('optionsUsers'))
    #ya no se necesitara            
    known_faces = detection_service.face_recognizer.get_known_faces()
    return render_template('add_face.html', known_faces=known_faces)

@app.route('/remove_face/<name>', methods=['POST'])
def remove_face(name):
    if 'username' not in session:
        return redirect(url_for('login'))
        
    if detection_service.face_recognizer.remove_face(name):
        flash(f'Face removed successfully for {name}')
    else:
        flash('Error removing face')
        
    return redirect(url_for('optionsUsers'))


















# Run the application
if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)



