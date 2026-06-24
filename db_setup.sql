-- Database setup script for CareBlink - Smart Eye Blink Emergency Alert System

-- Create Database
CREATE DATABASE IF NOT EXISTS careblink;
USE careblink;

-- Create Patients Table
CREATE TABLE IF NOT EXISTS patients (
    id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    age INT NOT NULL,
    room_number VARCHAR(20) NOT NULL,
    medical_condition VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create Alerts Table
CREATE TABLE IF NOT EXISTS alerts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id VARCHAR(50) NOT NULL,
    message VARCHAR(255) NOT NULL,
    status ENUM('active', 'dismissed') DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP NULL,
    FOREIGN KEY (patient_id) REFERENCES patients(patient_id) ON DELETE CASCADE
);

-- Insert Default Demo Patients
INSERT INTO patients (patient_id, name, age, room_number, medical_condition)
VALUES 
('PT-2045', 'Arthur Dent', 42, 'Room 101', 'Locked-in Syndrome (Non-verbal, full eye mobility)'),
('PT-3091', 'Sarah Connor', 35, 'Room 304', 'Severe Motor Neurone Disease (MND)')
ON DUPLICATE KEY UPDATE name=name;
