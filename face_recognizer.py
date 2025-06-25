import os
import numpy as np
import torch
import cv2
from facenet_pytorch import InceptionResnetV1
from PIL import Image
import pickle
from sklearn.preprocessing import StandardScaler
from datetime import datetime

class FaceRecognizer:
    def __init__(self, model_path='models/facenet.pt', database_path='face_database'):
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.model = InceptionResnetV1(pretrained='vggface2').eval().to(self.device)
        self.database_path = database_path
        os.makedirs(database_path, exist_ok=True)
        self.embeddings_file = os.path.join(database_path, 'embeddings.pkl')
        self.load_database()
        self.similarity_threshold = 0.8

    def load_database(self):
        """Load existing face embeddings database"""
        try:
            with open(self.embeddings_file, 'rb') as f:
                data = pickle.load(f)
                # Convertir formato antiguo al nuevo si es necesario
                if data and isinstance(next(iter(data.values())), np.ndarray):
                    print("Converting old database format to new format...")
                    self.known_embeddings = {
                        name: {'embeddings': [embedding], 'count': 1}
                        for name, embedding in data.items()
                    }
                else:
                    self.known_embeddings = data
            print(f"Loaded database with {len(self.known_embeddings)} people")
        except (FileNotFoundError, EOFError):
            self.known_embeddings = {}
            print("Created new face embeddings database")

    def save_database(self):
        """Save face embeddings database"""
        with open(self.embeddings_file, 'wb') as f:
            pickle.dump(self.known_embeddings, f)

    def get_embedding(self, face_img):
        """Convert face image to embedding vector"""
        try:
            if len(face_img.shape) == 2:
                face_img = cv2.cvtColor(face_img, cv2.COLOR_GRAY2RGB)
            elif face_img.shape[2] == 4:
                face_img = cv2.cvtColor(face_img, cv2.COLOR_BGRA2RGB)
            elif face_img.shape[2] == 3:
                face_img = cv2.cvtColor(face_img, cv2.COLOR_BGR2RGB)
                
            face_img = cv2.resize(face_img, (160, 160))
            face_tensor = torch.from_numpy(face_img).float()
            face_tensor = face_tensor.permute(2, 0, 1).unsqueeze(0)
            face_tensor = face_tensor.to(self.device)
            
            with torch.no_grad():
                embedding = self.model(face_tensor).cpu().numpy()[0]
            return embedding
            
        except Exception as e:
            print(f"Error in get_embedding: {e}")
            raise

    def add_face(self, face_img, name):
        """Add a new face to the database"""
        try:
            print(f"Adding new face image for {name}")
            embedding = self.get_embedding(face_img)
            
            if name not in self.known_embeddings:
                self.known_embeddings[name] = {
                    'embeddings': [embedding],
                    'count': 1
                }
            else:
                # Limit to maximum 5 images per person
                if self.known_embeddings[name]['count'] >= 5:
                    print("Maximum number of images reached for this person")
                    return False
                    
                self.known_embeddings[name]['embeddings'].append(embedding)
                self.known_embeddings[name]['count'] += 1
            
            self.save_database()
            
            # Save face image with index
            count = self.known_embeddings[name]['count']
            img_filename = f"{name}_{count}.jpg"
            img_path = os.path.join(self.database_path, img_filename)
            cv2.imwrite(img_path, face_img)
            
            print(f"Successfully added face {count} for {name}")
            return True
            
        except Exception as e:
            print(f"Error in add_face: {e}")
            import traceback
            print(traceback.format_exc())
            return False

    def recognize_face(self, face_img):
        """Recognize a face from the database"""
        try:
            if not self.known_embeddings:
                return None, 0.0
                
            test_embedding = self.get_embedding(face_img)
            max_similarity = -1
            best_match = None
            
            for name, data in self.known_embeddings.items():
                # Calculate similarity with all embeddings for this person
                similarities = [np.dot(test_embedding, emb) 
                              for emb in data['embeddings']]
                
                max_similarity_person = max(similarities)
                if max_similarity_person > max_similarity:
                    max_similarity = max_similarity_person
                    best_match = name
            
            if max_similarity > self.similarity_threshold:
                return best_match, float(max_similarity)
            else:
                return None, float(max_similarity)
                
        except Exception as e:
            print(f"Error in recognize_face: {e}")
            return None, 0.0

    def remove_face(self, name):
        """Remove all faces for a person from the database"""
        if name in self.known_embeddings:
            count = self.known_embeddings[name]['count']
            # Remove all saved images
            for i in range(1, count + 1):
                img_path = os.path.join(self.database_path, f"{name}_{i}.jpg")
                try:
                    os.remove(img_path)
                except OSError:
                    pass
                    
            del self.known_embeddings[name]
            self.save_database()
            return True
        return False

    def get_known_faces(self):
        """Get dictionary of known faces with their image counts"""
        try:
            return {name: data['count'] for name, data in self.known_embeddings.items()}
        except:
            # Fallback for old format
            return {name: 1 for name in self.known_embeddings.keys()}