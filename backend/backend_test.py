#!/usr/bin/env python3
"""
DuoVocab Duel Backend API Testing
Tests all API endpoints for the vocabulary game
"""

import requests
import sys
import json
from datetime import datetime
import time

class DuoVocabTester:
    def __init__(self, base_url="http://localhost:8000/api"):
        self.base_url = base_url
        self.tests_run = 0
        self.tests_passed = 0
        self.user1_id = None
        self.user2_id = None
        self.room_id = None
        self.room_code = None
        
    def log(self, message):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
        
    def run_test(self, name, method, endpoint, expected_status, data=None, params=None):
        """Run a single API test"""
        url = f"{self.base_url}/{endpoint}"
        headers = {'Content-Type': 'application/json'}
        
        self.tests_run += 1
        self.log(f"🔍 Testing {name}...")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, params=params)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers)
            
            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                self.log(f"✅ {name} - Status: {response.status_code}")
                try:
                    return True, response.json()
                except:
                    return True, {}
            else:
                self.log(f"❌ {name} - Expected {expected_status}, got {response.status_code}")
                try:
                    error_detail = response.json()
                    self.log(f"   Error: {error_detail}")
                except:
                    self.log(f"   Response: {response.text}")
                return False, {}
                
        except Exception as e:
            self.log(f"❌ {name} - Error: {str(e)}")
            return False, {}
    
    def test_root_endpoint(self):
        """Test API root endpoint"""
        return self.run_test("API Root", "GET", "", 200)
    
    def test_word_count(self):
        """Test word count endpoint"""
        success, response = self.run_test("Word Count", "GET", "words/count", 200)
        if success and response:
            total = response.get('total', 0)
            by_level = response.get('by_level', {})
            self.log(f"   Total words: {total}")
            self.log(f"   By level: {by_level}")
            if total >= 50:
                self.log("   ✅ Has required 50+ words")
            else:
                self.log(f"   ⚠️  Only {total} words found, expected 50+")
        return success, response
    
    def test_guest_auth(self, nickname):
        """Test guest authentication"""
        success, response = self.run_test(
            f"Guest Auth ({nickname})", 
            "POST", 
            "auth/guest", 
            200,
            data={"nickname": nickname}
        )
        if success and response:
            user_id = response.get('user_id')
            returned_nickname = response.get('nickname')
            self.log(f"   User ID: {user_id}")
            self.log(f"   Nickname: {returned_nickname}")
            return success, user_id
        return success, None
    
    def test_create_room(self, user_id, mode="classic", target_score=10):
        """Test room creation"""
        success, response = self.run_test(
            f"Create Room ({mode})", 
            "POST", 
            "rooms", 
            200,
            data={
                "user_id": user_id,
                "mode": mode,
                "target_score": target_score
            }
        )
        if success and response:
            room_id = response.get('room_id')
            code = response.get('code')
            self.log(f"   Room ID: {room_id}")
            self.log(f"   Room Code: {code}")
            return success, room_id, code
        return success, None, None
    
    def test_join_room(self, code, user_id):
        """Test joining a room"""
        success, response = self.run_test(
            "Join Room", 
            "POST", 
            f"rooms/{code}/join", 
            200,
            data={"user_id": user_id}
        )
        return success, response
    
    def test_room_state(self, code, user_id):
        """Test getting room state"""
        success, response = self.run_test(
            "Room State", 
            "GET", 
            f"rooms/{code}/state", 
            200,
            params={"user_id": user_id}
        )
        if success and response:
            status = response.get('status')
            players = response.get('players', [])
            current_turn = response.get('current_turn')
            self.log(f"   Status: {status}")
            self.log(f"   Players: {len(players)}")
            if current_turn:
                self.log(f"   Current turn: {current_turn.get('word_ua', 'N/A')}")
        return success, response
    
    def test_submit_answer(self, code, user_id, answer):
        """Test submitting an answer"""
        success, response = self.run_test(
            f"Submit Answer ({answer})", 
            "POST", 
            f"rooms/{code}/turn", 
            200,
            data={
                "user_id": user_id,
                "answer": answer
            }
        )
        if success and response:
            points = response.get('points', 0)
            feedback = response.get('feedback', 'unknown')
            correct_answer = response.get('correct_answer', 'N/A')
            self.log(f"   Points: {points}")
            self.log(f"   Feedback: {feedback}")
            self.log(f"   Correct: {correct_answer}")
        return success, response
    
    def test_invalid_scenarios(self):
        """Test error handling scenarios"""
        self.log("\n🔍 Testing Error Scenarios...")
        
        # Test invalid nickname (too short)
        self.run_test("Invalid Nickname", "POST", "auth/guest", 422, 
                     data={"nickname": "a"})
        
        # Test joining non-existent room
        if self.user1_id:
            self.run_test("Join Invalid Room", "POST", "rooms/INVALID/join", 404,
                         data={"user_id": self.user1_id})
        
        # Test room state for non-existent room
        if self.user1_id:
            self.run_test("Invalid Room State", "GET", "rooms/INVALID/state", 404,
                         params={"user_id": self.user1_id})
    
    def run_full_game_flow(self):
        """Test complete game flow"""
        self.log("\n🎮 Testing Complete Game Flow...")
        
        # 1. Test API root
        success, _ = self.test_root_endpoint()
        if not success:
            return False
        
        # 2. Test word count
        success, _ = self.test_word_count()
        if not success:
            return False
        
        # 3. Create two users
        success, self.user1_id = self.test_guest_auth("Player1")
        if not success:
            return False
            
        success, self.user2_id = self.test_guest_auth("Player2")
        if not success:
            return False
        
        # 4. Create room
        success, self.room_id, self.room_code = self.test_create_room(self.user1_id, "classic", 5)
        if not success:
            return False
        
        # 5. Check room state (waiting)
        success, state = self.test_room_state(self.room_code, self.user1_id)
        if not success:
            return False
        
        # 6. Second player joins
        success, _ = self.test_join_room(self.room_code, self.user2_id)
        if not success:
            return False
        
        # 7. Check room state (should be playing now)
        time.sleep(1)  # Allow time for game to start
        success, state = self.test_room_state(self.room_code, self.user1_id)
        if not success:
            return False
        
        # 8. Test game turns (simulate a few moves)
        if state and state.get('status') == 'playing':
            self.log("\n🎯 Testing Game Turns...")
            
            for turn in range(3):  # Test 3 turns
                # Get current state
                success, state = self.test_room_state(self.room_code, self.user1_id)
                if not success:
                    break
                
                current_turn = state.get('current_turn')
                if not current_turn:
                    self.log("   No active turn found")
                    break
                
                current_player_id = current_turn.get('current_player_id')
                word_ua = current_turn.get('word_ua')
                
                self.log(f"   Turn {turn + 1}: {word_ua}")
                
                # Submit a test answer (intentionally wrong to test scoring)
                test_answer = "test_answer"
                success, response = self.test_submit_answer(self.room_code, current_player_id, test_answer)
                if not success:
                    break
                
                time.sleep(1)  # Allow turn processing
        
        # 9. Test challenge mode
        self.log("\n⚡ Testing Challenge Mode...")
        success, room_id2, room_code2 = self.test_create_room(self.user1_id, "challenge", 3)
        if success:
            success, _ = self.test_join_room(room_code2, self.user2_id)
            if success:
                time.sleep(1)
                success, state = self.test_room_state(room_code2, self.user1_id)
                if success and state:
                    current_turn = state.get('current_turn')
                    if current_turn and current_turn.get('time_remaining') is not None:
                        self.log(f"   ✅ Challenge mode timer working: {current_turn.get('time_remaining')}s")
        
        return True
    
    def run_all_tests(self):
        """Run all tests"""
        self.log("🚀 Starting DuoVocab Duel API Tests")
        self.log(f"   Base URL: {self.base_url}")
        
        # Run full game flow
        success = self.run_full_game_flow()
        
        # Test error scenarios
        self.test_invalid_scenarios()
        
        # Print summary
        self.log(f"\n📊 Test Results:")
        self.log(f"   Tests run: {self.tests_run}")
        self.log(f"   Tests passed: {self.tests_passed}")
        self.log(f"   Success rate: {(self.tests_passed/self.tests_run*100):.1f}%")
        
        if self.tests_passed == self.tests_run:
            self.log("🎉 All tests passed!")
            return 0
        else:
            self.log("❌ Some tests failed")
            return 1

def main():
    tester = DuoVocabTester()
    return tester.run_all_tests()

if __name__ == "__main__":
    sys.exit(main())