#include <Servo.h>

Servo servoB;  // Зона B (пин 9)
Servo servoC;  // Зона C (пин 10)
Servo servoD;  // Зона D (пин 11)

const int LED_PIN = LED_BUILTIN;

void setup() {
  Serial.begin(115200);
  
  servoB.attach(9);
  servoC.attach(10);
  servoD.attach(11);
  
  servoB.write(90);
  servoC.write(90);
  servoD.write(90);
  
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
  
  Serial.println("Ready");
}

void loop() {
  if (Serial.available() > 0) {
    char cmd = Serial.read();
    if (cmd == '\n' || cmd == '\r') return;
    
    digitalWrite(LED_PIN, HIGH);
    
    switch (cmd) {
      case '1':
        moveServo(servoB, 0);
        Serial.println("OK");
        break;
      case '2':
        moveServo(servoC, 90);
        Serial.println("OK");
        break;
      case '3':
        moveServo(servoD, 180);
        Serial.println("OK");
        break;
      case '0':
        moveServo(servoB, 90);
        moveServo(servoC, 90);
        moveServo(servoD, 90);
        Serial.println("OK");
        break;
      default:
        Serial.println("ERR");
        break;
    }
    
    digitalWrite(LED_PIN, LOW);
  }
}

void moveServo(Servo &servo, int targetAngle) {
  int current = servo.read();
  if (current == targetAngle) return;
  
  if (current < targetAngle) {
    for (int i = current; i <= targetAngle; i++) {
      servo.write(i);
      delay(15);
    }
  } else {
    for (int i = current; i >= targetAngle; i--) {
      servo.write(i);
      delay(15);
    }
  }
  delay(100);
}