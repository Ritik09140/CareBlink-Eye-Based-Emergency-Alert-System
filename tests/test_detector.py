import unittest
import math

class MockLandmark:
    def __init__(self, x, y):
        self.x = x
        self.y = y

class TestDetectorMath(unittest.TestCase):
    def distance(self, p1, p2):
        return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)

    def calculate_ear(self, landmarks, horizontal_idx, vertical_idxs, w, h):
        h_p1 = (int(landmarks[horizontal_idx[0]].x * w), int(landmarks[horizontal_idx[0]].y * h))
        h_p2 = (int(landmarks[horizontal_idx[1]].x * w), int(landmarks[horizontal_idx[1]].y * h))
        
        v_dists = []
        for top_idx, bot_idx in vertical_idxs:
            top_p = (int(landmarks[top_idx].x * w), int(landmarks[top_idx].y * h))
            bot_p = (int(landmarks[bot_idx].x * w), int(landmarks[bot_idx].y * h))
            v_dists.append(self.distance(top_p, bot_p))
            
        h_dist = self.distance(h_p1, h_p2)
        if h_dist == 0:
            return 0.0
            
        avg_v_dist = sum(v_dists) / len(vertical_idxs)
        return avg_v_dist / h_dist

    def test_ear_calculation(self):
        # Create a mockup of face landmarks
        # landmarks indices: 33, 133 for horizontal left eye
        # vertical pairs: (160, 144), (159, 145), (158, 153)
        landmarks = {}
        
        # Horizontal width: 100 pixels (from x=0.1 to x=0.3 on image width=500)
        landmarks[33] = MockLandmark(0.1, 0.5)
        landmarks[133] = MockLandmark(0.3, 0.5)
        
        # Vertical height: 20 pixels average
        # Vertical pair 1
        landmarks[160] = MockLandmark(0.15, 0.48)
        landmarks[144] = MockLandmark(0.15, 0.52) # diff = 0.04 * 500 = 20px
        
        # Vertical pair 2
        landmarks[159] = MockLandmark(0.20, 0.48)
        landmarks[145] = MockLandmark(0.20, 0.52) # diff = 20px
        
        # Vertical pair 3
        landmarks[158] = MockLandmark(0.25, 0.48)
        landmarks[153] = MockLandmark(0.25, 0.52) # diff = 20px
        
        w, h = 500, 500
        ear = self.calculate_ear(
            landmarks, 
            horizontal_idx=(33, 133), 
            vertical_idxs=[(160, 144), (159, 145), (158, 153)], 
            w=w, h=h
        )
        
        # Horizontal dist = 0.2 * 500 = 100
        # Vertical average dist = 20
        # EAR = 20 / 100 = 0.20
        self.assertAlmostEqual(ear, 0.20, places=2)

if __name__ == '__main__':
    unittest.main()
