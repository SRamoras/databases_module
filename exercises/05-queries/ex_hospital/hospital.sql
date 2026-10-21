CREATE DATABASE IF NOT EXISTS hospital;
USE hospital;

CREATE TABLE Patients (
    id INT PRIMARY KEY,
    name VARCHAR(40),
    nif VARCHAR(9),
    phone_number VARCHAR(20),
    email VARCHAR(150) UNIQUE NOT NULL
);

CREATE TABLE Cases (
    id INT PRIMARY KEY,
    name VARCHAR(40),
    patient_id INT,
    FOREIGN KEY (patient_id) REFERENCES Patients(id)
);

CREATE TABLE Episode (
    id INT PRIMARY KEY,
    name VARCHAR(40),
    case_id INT,
    FOREIGN KEY (case_id) REFERENCES Cases(id)
);

CREATE TABLE Medical_Units (
    id INT PRIMARY KEY,
    name VARCHAR(40),
    episode_id INT,
    FOREIGN KEY (episode_id) REFERENCES Episode(id)
);

CREATE TABLE Units (
    id INT PRIMARY KEY,
    name VARCHAR(40),
    medical_unit_id INT,
    FOREIGN KEY (medical_unit_id) REFERENCES Medical_Units(id)
);

CREATE TABLE Rooms (
    id INT PRIMARY KEY,
    name VARCHAR(40),
    unit_id INT,
    FOREIGN KEY (unit_id) REFERENCES Units(id)
);

CREATE TABLE Staffs (
    id INT PRIMARY KEY,
    name VARCHAR(40),
    nif VARCHAR(9),
    phone_number VARCHAR(20),
    email VARCHAR(150) UNIQUE NOT NULL
);

CREATE TABLE Shift (
    id INT PRIMARY KEY,
    start_time DATETIME,
    end_time DATETIME,
    name VARCHAR(40),
    unit_id INT,
    staff_id INT,
    FOREIGN KEY (unit_id) REFERENCES Units(id),
    FOREIGN KEY (staff_id) REFERENCES Staffs(id)
);

CREATE TABLE Episodes_Staffs (
    FOREIGN KEY (episode_id) REFERENCES Episode(id),
    FOREIGN KEY (staff_id) REFERENCES Staffs(id)
);

CREATE TABLE Finances (
    id INT PRIMARY KEY,
    cost DECIMAL(10,2),
    createdAt TIMESTAMP,
    case_id INT,
    FOREIGN KEY (case_id) REFERENCES Cases(id)
);

CREATE TABLE Reports (
    id INT PRIMARY KEY,
    cost DECIMAL(10,2),
    createdAt TIMESTAMP,
    case_id INT,
    FOREIGN KEY (case_id) REFERENCES Cases(id)
);

CREATE TABLE Insurances (
    id INT PRIMARY KEY,
    name VARCHAR(30),
    createdAt TIMESTAMP,
    case_id INT,
    FOREIGN KEY (case_id) REFERENCES Cases(id)
);

CREATE TABLE Finance_Insurance (
    FOREIGN KEY (finance_id) REFERENCES Finances(id),
    FOREIGN KEY (insurance_id) REFERENCES Insurances(id)
);