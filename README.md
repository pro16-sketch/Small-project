# Online Exam Proctoring System

A comprehensive web-based exam proctoring system built with Flask that monitors students during online exams using webcam surveillance, tab-switching detection, and other anti-cheating measures.

## Features

### 🎓 Student Features
- User registration and authentication
- View available exams
- Take proctored exams with real-time monitoring
- View exam results and history
- Automatic exam submission on time expiry

### 👨‍💼 Admin Features
- Create and manage exams
- Add multiple-choice questions with points
- View all student violations
- Monitor exam sessions with detailed analytics
- Review webcam snapshots and proctoring data
- Track student performance

### 🔒 Proctoring Features
- **Real-Time AI Face Detection**: Uses Gemini vision model to accurately detect faces
- **Webcam Monitoring**: Continuous video feed recording
- **Face Detection**: AI-powered detection alerts when no face or multiple faces detected
- **Tab Switching Detection**: Logs when student leaves exam page
- **Copy/Paste Prevention**: Blocks copying and pasting
- **Context Menu Blocking**: Disables right-click
- **Developer Tools Prevention**: Blocks F12 and inspect element
- **Automatic Snapshots**: Captures periodic images during exam
- **Violation Tracking**: Records all suspicious activities with debouncing to prevent duplicates
- **Auto-Ban System**: Students with >20 violations are permanently banned from the exam
- **Real-time Timer**: Countdown timer with auto-submit

## Installation

1. Install Python 3.8 or higher

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the application:
```bash
python app.py
```

4. Access the application:
   - Open browser and go to: http://127.0.0.1:5000

## AI Features (Gemini API)

This project uses Google's Gemini API for two AI-powered features:

### 1. AI Question Generation

Auto-generate multiple-choice questions using a Gemini LLM.

### 2. Real-Time Face Detection (Vision Model)

AI-powered face detection for accurate proctoring during exams.

### API Configuration & Setup

1. **Get a Gemini API Key**:
    - Obtain an API key from Google AI Studio.

2. **Configure Environment Variables**:
    - Create a `.env` file in the root of the project (copy from `.env.example`):
      ```env
      GEMINI_API_KEY=your_actual_gemini_api_key_here
      ```
    - Alternatively, set it in your system or terminal environment:
      ```powershell
      $env:GEMINI_API_KEY = "your_actual_gemini_api_key_here"
      ```

3. **(Optional) Customize Models**:
    - You can customize the models used by setting environment variables in `.env`:
      ```env
      GEMINI_MODEL=gemini-1.5-flash
      GEMINI_VISION_MODEL=gemini-1.5-flash
      ```

### Python Dependencies

The app uses the Python `google-generativeai` client. Ensure dependencies are installed:

```powershell
pip install -r requirements.txt
```

### Using AI Features in the App

**Question Generation:**
- As an admin, open the "Add Questions" page for an exam.
- Use the "Generate with AI (Ollama)" panel to enter a topic and the number of questions.
- Click "Generate Questions". The app will generate and insert questions automatically.

**Face Detection:**
- Runs automatically during exams every 15 seconds
- Accurately detects 0, 1, or multiple faces in the webcam feed
- Shows real-time status: ✅ 1 face detected, ❌ No face, ⚠️ Multiple faces
- Logs violations only when anomalies are detected (not random)
- Includes 5-second cooldown to prevent duplicate violations

### Troubleshooting

**AI Question Generation Issues:**
- If generation fails, make sure:
  - Your `GEMINI_API_KEY` is set correctly in `.env` or system environment variables.
  - You have an active internet connection to communicate with the Gemini API.

**Face Detection Issues:**
- If face detection shows errors:
  - Verify your `GEMINI_API_KEY` is valid.
  - Check browser console for detailed error messages.
  - Verify webcam access is granted in browser.
  
**False Positives/Negatives:**
- The AI model (gemini-1.5-flash) is highly accurate and analyzes actual faces.
- If detection seems wrong, ensure good lighting in your room.
- The system includes a 5-second cooldown to prevent duplicate violations.
- Each check happens every 15 seconds (not continuous to reduce server load).

## Default Credentials

**Admin Account:**
- Username: `admin`
- Password: `admin123`

**Student Accounts:**
- Register new student accounts via the registration page

## Usage

### For Administrators:

1. Login with admin credentials
2. Create a new exam from the dashboard
3. Add questions with multiple choices and correct answers
4. Students can now take the exam
5. Monitor violations and review exam sessions
6. View detailed reports with snapshots and analytics

### For Students:

1. Register a new account
2. Login to student dashboard
3. View available exams
4. Click "Start Exam" to begin (webcam access required)
5. Answer questions within time limit
6. Submit exam when complete
7. View results on dashboard

## Proctoring Rules

During exams, students must:
- Keep face visible in webcam at all times
- Stay on exam page (no tab switching)
- Not use copy/paste functions
- Not open developer tools
- Complete exam within time limit

All violations are logged and reported to administrators.

## Database Schema

The system uses SQLite with the following tables:
- `users`: User accounts (students and admins)
- `exams`: Exam definitions
- `questions`: Exam questions and answers
- `exam_sessions`: Active and completed exam attempts
- `answers`: Student responses
- `violations`: Proctoring violations
- `snapshots`: Webcam captures

## Security Features

- Password hashing using Werkzeug
- Session management with secure cookies
- Role-based access control (admin/student)
- CSRF protection via Flask sessions
- Input validation and sanitization

## Technology Stack

- **Backend**: Flask (Python)
- **Database**: SQLite
- **Frontend**: HTML5, CSS3, JavaScript
- **Webcam**: WebRTC/getUserMedia API
- **Image Processing**: OpenCV (for future face detection enhancement)

## Future Enhancements

- Real-time face detection using face-api.js or OpenCV
- Screen recording capability
- Live proctoring with video calls
- AI-based suspicious behavior detection
- Mobile app support
- Integration with LMS platforms
- Advanced analytics dashboard
- Email notifications for violations

## File Structure

```
project/
│
├── app.py                 # Main Flask application
├── database.db            # SQLite database
├── requirements.txt       # Python dependencies
├── README.md             # This file
│
├── templates/            # HTML templates
│   ├── login.html
│   ├── register.html
│   ├── admin_dashboard.html
│   ├── student_dashboard.html
│   ├── create_exam.html
│   ├── add_questions.html
│   ├── take_exam.html
│   ├── violations.html
│   └── session_details.html
│
└── static/              # Static files
    └── uploads/         # Webcam snapshots
```

## License

This project is open source and available for educational purposes.

## Support

For issues or questions, please create an issue in the repository.

---

**Note**: This is a demonstration project. For production use, additional security measures, scalability improvements, and compliance with privacy regulations should be implemented.
