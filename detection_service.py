import cv2
import numpy as np
from threading import Thread, Lock
import time
import json
import torch
from collections import defaultdict, deque
from queue import Queue, Empty
#import threading
from mtcnn import MTCNN
from face_recognizer import FaceRecognizer
from telegram_service import TelegramNotifier
import asyncio
from concurrent.futures import ThreadPoolExecutor
from ultralytics import YOLO
import sys
import os
from contextlib import redirect_stdout

#model = torch.hub.load('ultralytics/yolov5', 'yolov5s', pretrained=True)
class CameraDetectionService:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(CameraDetectionService, cls).__new__(cls)
            cls._instance.initialized = False
        return cls._instance
    
    def __init__(self):
        if not self.initialized:
            
            
            # Initialize face detection and recognition
            self.face_detector = MTCNN()
            self.face_recognizer = FaceRecognizer()
            
            self.yolo = YOLO('yolo11n.pt',verbose=False)

            # Thread pool for face recognition
            self.executor = ThreadPoolExecutor(max_workers=3) #??

            self.cameras = {}
            self.lock = Lock()
            self.frame_queues = defaultdict(lambda: Queue(maxsize=10))
            self.detection_queues = defaultdict(lambda: Queue(maxsize=10))
            self.active = True
            self.initialized = True

            # Performance monitoring
            self.processing_times = deque(maxlen=50)
            self.skip_frames = 15
            #self.detection_interval = 2

            # Object tracking
            
            #Set telegram bot 
            self.telegram_notifier = TelegramNotifier(bot_token='8037991386:AAGfIkEFKA-kTjeVlqiL_xTSaY8u3XJ-rUc', chat_id='6346231670')

          

            # Start detection automatically
            #self.start_detection()

           
            

    async def process_face_recognition(self, face_img):
        """Reconoce un rostro en la base de datos."""
        try:
            name, confidence = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                self.face_recognizer.recognize_face,
                face_img
            )
            print(f"FUncion reconocimiento de rostros")
            return name, confidence
        except Exception as e:
            print(f"Error en reconocimiento facial: {e}")
            return None, 0.0

    def _capture_frames(self, camera_id, url):
        """Continuously capture frames from camera"""
        cap = cv2.VideoCapture(url)

        if not cap.isOpened():
            print(f"Failed to open camera {camera_id}")            
            
            return

        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        consecutive_failures = 0  # Contador de fallos consecutivos para detectar desconexión
        max_failures = 7  # Número de intentos fallidos antes de considerar la cámara apagada

        while self.cameras[camera_id]['active']:
            ret, frame = cap.read()

            if not ret:
                consecutive_failures += 1
                

                if consecutive_failures >= max_failures:
                    
                    self.telegram_notifier.send_telegram_alert(f"🚨 La cámara {camera_id} se ha desconectado!")
                    self.cameras[camera_id]['active'] = False
                    break  # Salir del bucle

                time.sleep(0.5)  # Espera antes de volver a intentar
                continue
            else:
                consecutive_failures = 0  # Resetear contador si la captura vuelve a funcionar

            # Limpiar la cola si está llena
            if self.frame_queues[camera_id].full():
                #print(f"Queue full for camera {camera_id}, clearing queue...")
                with self.lock:
                    while not self.frame_queues[camera_id].empty():
                        self.frame_queues[camera_id].get_nowait()

            self.frame_queues[camera_id].put((frame, time.time()))

        cap.release()

    ##--------------
    def detect_people(self, frame):
        """Detecta personas en el frame usando YOLO."""
        with open(os.devnull, 'w') as f, redirect_stdout(f):  # Redirige stdout a un archivo vacío
            results = self.yolo.predict(frame, verbose=False) 
        
        people_boxes = []
        for result in results:
            xyxy_boxes = result.boxes.xyxy.cpu().numpy()  # Obtener las coordenadas
            confs = result.boxes.conf.cpu().numpy()  # Obtener las confianzas
            classes = result.boxes.cls.cpu().numpy().astype(int)  # Obtener las clases

            for i in range(len(classes)):  # Iterar manualmente
                x1, y1, x2, y2 = map(int, xyxy_boxes[i])
                conf = confs[i]
                cls = classes[i]
                
                if cls == 0 and conf > 0.8:  # Filtra solo personas
                    #print("Personas detectadas con % "+ str(conf))
                    people_boxes.append((x1, y1, x2, y2))

        return people_boxes

    async def detect_faces_in_people(self, frame, people_boxes):
        """Aplica MTCNN en las regiones donde YOLO detectó personas en paralelo usando async."""
        face_boxes = []

        async def process_person(x1, y1, x2, y2):
            """Función asíncrona que procesa una persona detectada y busca rostros."""
            person_roi = frame[y1:y2, x1:x2]
            faces = await asyncio.get_event_loop().run_in_executor(None, self.face_detector.detect_faces, person_roi)
            local_faces = []

            for face in faces:
                #print("Se encontro un rostro: " + str(face['confidence']))
                if face['confidence'] > 0.74:  # Filtrar confianza
                    fx, fy, fw, fh = face['box']
                    local_faces.append((x1 + fx, y1 + fy, x1 + fx + fw, y1 + fy + fh))  # Ajustar coordenadas

            return local_faces

        # Ejecutar todas las detecciones de rostros en paralelo
        tasks = [asyncio.create_task(process_person(*box)) for box in people_boxes]
        results = await asyncio.gather(*tasks)  # Esperar a que todas las tareas terminen

        # Unir todas las detecciones de rostros
        for res in results:
            face_boxes.extend(res)

        return face_boxes  # Retorna las caras detectadas


    #----------------
    
    def _process_detections(self, camera_id):
        frame_counter = 0
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loopD = asyncio.new_event_loop()
        asyncio.set_event_loop(loopD)
        fail_counter = 0
        #last_detection_time = 0  # Store the last detection time
        #DETECTION_INTERVAL = 2   # Time interval in seconds
        prev_frame = None
        while self.cameras[camera_id]['active']:
            try:
                frame, timestamp = self.frame_queues[camera_id].get(timeout=1.0)
                
                frame_counter += 1
                
                if frame_counter % self.skip_frames != 0:
                    continue
                
                
                # Comparar con frame anterior si existe
                # Detectar movimiento
                if prev_frame is not None and prev_frame.shape == frame.shape:
                    diff = cv2.absdiff(prev_frame, frame)
                    gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
                    _, thresh = cv2.threshold(gray, 30, 255, cv2.THRESH_BINARY)
                    if np.sum(thresh) < 5000:
                        prev_frame = frame
                        continue  # No hay cambio visible
                else:
                    prev_frame = frame
                    continue
                
                prev_frame = frame  # Actualizar para el próximo ciclo
                        
                
                



                print("Buscando personas")
                detections = []
                people_boxes = self.detect_people(frame)  
                
                if not people_boxes:
                    continue 
                print("Buscando rostro")
                #face_boxes = self.detect_faces_in_people(frame, people_boxes)
                face_boxes = loop.run_until_complete(self.detect_faces_in_people(frame, people_boxes))

                if not face_boxes:
                    fail_counter += 1
                    if fail_counter > 2:
                        print("ENVIANDO")
                        fail_counter = 0
                        alert_message = f"🚨 Desconocido detectado en la camara {camera_id} a las {time.strftime('%H:%M:%S')}"
                        self.telegram_notifier.send_image(frame, caption=alert_message)
                    #print("No se detectaron rostros para comparar")
                    continue
                
                fail_counter = 0
                print("BUscando parecido en base de datos")
                for (fx1, fy1, fx2, fy2) in face_boxes:
                    face_img = frame[fy1:fy2, fx1:fx2]  

                    name, confidence = loop.run_until_complete(
                        self.process_face_recognition(face_img)
                    )

                    detection_info = {
                        'class': 'face',
                        'confidence': float(confidence),
                        'box': (fx1, fy1, fx2, fy2),
                        'timestamp': timestamp
                    }
                            
                    if name is None:  # Only notify for unknown faces
                        #print("Similitud " + str(confidence))
                        alert_message = f"🚨 Desconocido detectado en la camara {camera_id} a las {time.strftime('%H:%M:%S')}"
                        # Send message + image
                        
                        self.telegram_notifier.send_image(frame, caption=alert_message)
                    # Add recognition results if a match was found
                    if name and confidence > 0.8:
                        #print("Se encontro usuario "+ name + " " + str(confidence))
                        alert_message = "Encontrado " + name + " con una similitud de " + str(confidence)
                        self.telegram_notifier.send_image(frame, caption=alert_message)
                    
                    detections.append(detection_info)
                    #print(f"Face detected in camera {camera_id}" + 
                    #      f" - Recognized as: {name if name else 'Unknown'} " + str(recognition_confidence))
                

                # Update detection queue
                if self.detection_queues[camera_id].full():
                    try:
                        self.detection_queues[camera_id].get_nowait()
                    except Empty:
                        pass
                self.detection_queues[camera_id].put((detections, timestamp))
                

            except Empty:
                continue
            except Exception as e:
                print(f"Error processing detections for camera {camera_id}: {e}")
                time.sleep(0.1)
        loopD.close()
        loop.close()
        

    def get_detections(self, camera_id):
        """Get latest detections for a camera"""
        try:
            detections, timestamp = self.detection_queues[camera_id].get_nowait()
            if time.time() - timestamp < 3.0:
                return detections
        except Empty:
            pass
        return []
    
 
    #NEW PROCCES TO START DETECTION
    def start_camera(self, camera_id):
         """Start a specific camera"""
         try:
             with open('rstp.json', 'r') as file:
                 camera_list = json.load(file)


             if camera_id not in camera_list:
                 return False
             
             url = camera_list[camera_id]['url']
             cap = cv2.VideoCapture(url)
             if not cap.isOpened():
                cap.release()
                return False
             cap.release()

             if camera_id not in self.cameras:
                 # Start capture thread
                 capture_thread = Thread(target=self._capture_frames, 
                                      args=(camera_id, camera_list[camera_id]['url']))
                 capture_thread.daemon = True

                 # Start detection thread
                 detection_thread = Thread(target=self._process_detections, 
                                        args=(camera_id,))
                 detection_thread.daemon = True

                 self.cameras[camera_id] = {
                     'url': camera_list[camera_id]['url'],
                     'active': True,
                     'capture_thread': capture_thread,
                     'detection_thread': detection_thread
                 }

                 capture_thread.start()
                 detection_thread.start()
                 return True

             elif not self.cameras[camera_id]['active']:
                 self.cameras[camera_id]['active'] = True

                 # Start new threads
                 capture_thread = Thread(target=self._capture_frames, 
                                      args=(camera_id, camera_list[camera_id]['url']))
                 capture_thread.daemon = True

                 detection_thread = Thread(target=self._process_detections, 
                                        args=(camera_id,))
                 detection_thread.daemon = True

                 self.cameras[camera_id]['capture_thread'] = capture_thread
                 self.cameras[camera_id]['detection_thread'] = detection_thread

                 capture_thread.start()
                 detection_thread.start()
                 return True

         except (FileNotFoundError, json.JSONDecodeError) as e:
             print(f"Error loading camera list: {e}")
             return False

         return False
    def stop_camera(self, camera_id):
        """Stop a specific camera"""
        if camera_id in self.cameras and self.cameras[camera_id]['active']:
            self.cameras[camera_id]['active'] = False

            # Clear camera's queues
            while not self.frame_queues[camera_id].empty():
                try:
                    self.frame_queues[camera_id].get_nowait()
                except Empty:
                    break

            while not self.detection_queues[camera_id].empty():
                try:
                    self.detection_queues[camera_id].get_nowait()
                except Empty:
                    break

            return True
        return False
    def delete_camera(self, camera_id):
        """Delete a camera from the system and reorder remaining camera IDs"""
        try:
            # Stop the camera if it's running
            if camera_id in self.cameras:
                self.stop_camera(camera_id)
                del self.cameras[camera_id]

            # Read the current camera list
            with open('rstp.json', 'r') as file:
                camera_list = json.load(file)

            if camera_id not in camera_list:
                return False

            # Create a list of cameras sorted by ID
            sorted_cameras = sorted([(int(k), v) for k, v in camera_list.items()])
            deleted_index = next(i for i, (k, _) in enumerate(sorted_cameras) if str(k) == str(camera_id))

            # Remove the camera to be deleted
            del sorted_cameras[deleted_index]

            # Create new camera list with reordered IDs
            new_camera_list = {}
            new_cameras = {}  # For updating self.cameras

            for new_id, (old_id, camera_info) in enumerate(sorted_cameras, 1):
                str_new_id = str(new_id)
                new_camera_list[str_new_id] = camera_info

                # Update running cameras if they exist
                if str(old_id) in self.cameras:
                    # Store the current state
                    active_state = self.cameras[str(old_id)]['active']
                    url = self.cameras[str(old_id)]['url']

                    # Stop the old camera instance
                    self.stop_camera(str(old_id))

                    # Create new camera entry
                    new_cameras[str_new_id] = {
                        'url': url,
                        'active': active_state
                    }

            # Save the reordered list
            with open('rstp.json', 'w') as file:
                json.dump(new_camera_list, file, indent=4)

            # Update running cameras
            self.cameras = new_cameras

            # Restart any active cameras with their new IDs
            for new_id, camera_info in new_cameras.items():
                if camera_info['active']:
                    self.start_camera(new_id)

            return True

        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Error managing camera list: {e}")
            return False
        except Exception as e:
            print(f"Unexpected error in delete_camera: {e}")
            return False
    def get_camera_status(self, camera_id):
        """Get the status of a specific camera"""
        if camera_id in self.cameras:
            return 'active' if self.cameras[camera_id]['active'] else 'stopped'
        return 'not_found'
    def get_all_cameras(self):
        """Get list of all cameras with their status"""
        try:
            with open('rstp.json', 'r') as file:
                camera_list = json.load(file)

            cameras = []
            for camera_id, info in camera_list.items():
                status = self.get_camera_status(camera_id)
                cameras.append({
                    'id': camera_id,
                    'url': info['url'],
                    'status': status
                })
            return cameras

        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Error loading camera list: {e}")
            return []
    def add_camera(self, url):
        """Add a new camera to the system"""
        try:
            # Test camera connection
            cap = cv2.VideoCapture(url)
            if not cap.isOpened():
                cap.release()
                return False, "Invalid camera URL"
            cap.release()

            # Add to JSON file
            with open('rstp.json', 'r') as file:
                camera_list = json.load(file)

            # Generate new camera ID
            new_id = str(max([int(k) for k in camera_list.keys()] + [0]) + 1)

            camera_list[new_id] = {'url': url}

            with open('rstp.json', 'w') as file:
                json.dump(camera_list, file)

            # Start the camera
            self.start_camera(new_id)

            return True, new_id

        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Error adding camera: {e}")
            return False, "Error saving camera configuration"
