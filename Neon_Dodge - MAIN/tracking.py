import cv2
import mediapipe as mp
import threading
import pygame
import numpy as np
from pygame.math import Vector2

class HandTracker:
    def __init__(self, width, height):
        self.width, self.height = width, height
        self.cap = cv2.VideoCapture(0)
        
        # Performance & FPS settings
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FPS, 60) 
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        self.mp_hands = mp.solutions.hands
        self.mp_draw = mp.solutions.drawing_utils
        
        # min_detection_confidence=0.2 helps track even when half the hand is off-screen
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            model_complexity=0, 
            max_num_hands=1,
            min_detection_confidence=0.2, 
            min_tracking_confidence=0.2
        )
        
        self.index_pos = Vector2(width // 2, height // 2)
        self._raw_pos  = Vector2(width // 2, height // 2)  # unsmoothed
        self.gesture_continue = False
        self.gesture_quit = False
        self.is_pointing = False
        self.raw_frame = None
        self.running = True
        
        self.thread = threading.Thread(target=self._update_loop, daemon=True)
        self.thread.start()

    def _update_loop(self):
        while self.running:
            success, frame = self.cap.read()
            if not success: continue

            frame = cv2.flip(frame, 1)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.hands.process(rgb_frame)
            
            self.gesture_continue = False
            self.gesture_quit = False
            
            if results.multi_hand_landmarks:
                for hand_landmarks in results.multi_hand_landmarks:
                    # DRAW THE SKELETON (Visible in preview)
                    self.mp_draw.draw_landmarks(
                        frame, 
                        hand_landmarks, 
                        self.mp_hands.HAND_CONNECTIONS,
                        self.mp_draw.DrawingSpec(color=(0,255,0), thickness=2, circle_radius=2),
                        self.mp_draw.DrawingSpec(color=(0,0,255), thickness=2)
                    )
                    
                    lm = hand_landmarks.landmark
                    # Track Index Tip (Point 8)
                    tip = lm[8]
                    
                    # --- EDGE FIX LOGIC ---
                    # We map 10%-90% of the camera to 0%-100% of the game screen
                    # This lets you reach the edges without your hand leaving the camera view
                    margin = 0.15
                    screen_x = np.interp(tip.x, [margin, 1.0 - margin], [0, self.width])
                    screen_y = np.interp(tip.y, [margin, 1.0 - margin], [0, self.height])
                    
                    self._raw_pos  = Vector2(screen_x, screen_y)
                    # Lerp 55% toward raw pos each frame — smooths camera noise
                    # while still feeling instant to the player
                    self.index_pos = self.index_pos.lerp(self._raw_pos, 0.55)
                    
                    # Simple pointing logic: index must be higher than its base
                    self.is_pointing = tip.y < lm[6].y 
                    
                    # Gestures for dodge.py menus
                    fingers_up = [lm[i].y < lm[i-2].y for i in [8, 12, 16, 20]]
                    if all(fingers_up): self.gesture_continue = True
                    if fingers_up[0] and fingers_up[1] and not fingers_up[2]: self.gesture_quit = True

            self.raw_frame = frame

    def draw_preview(self, surf):
        if self.raw_frame is not None:
            # Show the camera frame with the green landmarks drawn on it
            frame_rgb = cv2.cvtColor(self.raw_frame, cv2.COLOR_BGR2RGB)
            frame_surf = pygame.surfarray.make_surface(frame_rgb.swapaxes(0, 1))
            preview = pygame.transform.scale(frame_surf, (150, 110))
            surf.blit(preview, (10, self.height - 120))
            pygame.draw.rect(surf, (0, 255, 255), (10, self.height - 120, 150, 110), 2)

    def get_move_vec(self, player_pos):
        if not self.is_pointing: return Vector2(0, 0)
        diff = self.index_pos - player_pos
        return diff.normalize() if diff.length() > 2 else Vector2(0, 0)

    def release(self):
        self.running = False
        self.cap.release()
        self.hands.close()