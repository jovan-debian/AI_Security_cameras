import requests
import time
import cv2

class TelegramNotifier:
    def __init__(self, bot_token, chat_id):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.last_notification_time = 0  # Store last notification timestamp




    def send_image(self, image, caption="Detected face"):
        """Sends an image to Telegram."""
        current_time = time.time()

        # Check if enough time has passed (2 minutes)
        if current_time - self.last_notification_time >= 60:
            print("Sending image to Telegram...")
            url = f'https://api.telegram.org/bot{self.bot_token}/sendPhoto'
            
            # Validate the image
            if image is None or image.size == 0:
                print("Error: Empty image, skipping notification.")
                return
            
            # Encode image as JPEG
            success, img_encoded = cv2.imencode('.jpg', image)
            if not success:
                print("Error: Could not encode image.")
                return

            files = {'photo': ('detected_face.jpg', img_encoded.tobytes(), 'image/jpeg')}
            data = {'chat_id': self.chat_id, 'caption': caption}
            print("Sending image to Telegram...")
            try:
                print("1")
                response = requests.post(url, files=files, data=data, timeout=3)
                print("2")
                #print("⏱️ Tiempo de respuesta:", response.elapsed.total_seconds(), "segundos")
                if response.status_code == 200:
                    print("✅ Image sent successfully!")
                    self.last_notification_time = current_time
                else:
                    print(f"Failed to send image. Status Code: {response.status_code}, Response: {response.text}")
            except Exception as e:
                print(f"⚠️ Error sending image: {e}")
        
    def send_telegram_alert(self, message="Alert!"):
        """Sends an text to Telegram."""
        current_time = time.time()

        # Check if enough time has passed (2 minutes)
        url = f'https://api.telegram.org/bot{self.bot_token}/sendMessage'
        
        data = {'chat_id': self.chat_id, 'text': message}
        try:
            response = requests.post(url, data=data)
            if response.status_code == 200:
                print(" Message sent successfully!")
                self.last_notification_time = current_time
            else:
                print(f"❌ Failed to send image. Status Code: {response.status_code}, Response: {response.text}")
        except Exception as e:
            print(f"⚠️ Error sending image: {e}")
