-- =====================================================
-- POPULATE DOCTORS
-- =====================================================
-- Using fixed UUIDs to easily map relationships in subsequent tables

INSERT INTO doctors (id, first_name, last_name, email, phone_number, license_number, specialization, years_experience, qualification, hospital_affiliation, consultation_fee, consultation_duration, bio)
VALUES
    ('11111111-1111-1111-1111-111111111111', 'Arjun', 'Kumar', 'arjun.kumar@example.com', '+919876543210', 'MCI-1001', 'General Physician', 15, 'MBBS, MD (General Medicine)', 'City Central Hospital', 500.00, 30, 'Experienced general physician specializing in holistic health and preventive medicine.'),

    ('22222222-2222-2222-2222-222222222222', 'Priya', 'Sharma', 'priya.sharma@example.com', '+919876543211', 'MCI-1002', 'Dermatologist', 8, 'MBBS, MD (Dermatology)', 'SkinCare Clinic', 800.00, 20, 'Passionate about treating clinical skin conditions and promoting skin health.'),

    ('33333333-3333-3333-3333-333333333333', 'Rahul', 'Verma', 'rahul.verma@example.com', '+919876543212', 'MCI-1003', 'Cardiologist', 20, 'MBBS, MD, DM (Cardiology)', 'Heart Care Institute', 1200.00, 30, 'Senior cardiologist with expertise in interventional cardiology and heart failure management.'),

    ('44444444-4444-4444-4444-444444444444', 'Ananya', 'Desai', 'ananya.desai@example.com', '+919876543213', 'MCI-1004', 'Pediatrician', 12, 'MBBS, MD (Pediatrics)', 'Kids Wellness Center', 600.00, 30, 'Friendly and dedicated pediatrician, ensuring the healthy growth of young children.');


-- =====================================================
-- POPULATE DOCTOR AVAILABILITY
-- =====================================================
-- Note: day_of_week is 0 (Sunday) to 6 (Saturday)

-- Dr. Arjun Kumar (General Physician)
-- Available Monday to Friday, 09:00 to 17:00, 30 min slots, 0 break
INSERT INTO doctor_availability (doctor_id, day_of_week, start_time, end_time, slot_duration, break_duration) VALUES
    ('11111111-1111-1111-1111-111111111111', 1, '09:00', '17:00', 30, 0), -- Mon
    ('11111111-1111-1111-1111-111111111111', 2, '09:00', '17:00', 30, 0), -- Tue
    ('11111111-1111-1111-1111-111111111111', 3, '09:00', '17:00', 30, 0), -- Wed
    ('11111111-1111-1111-1111-111111111111', 4, '09:00', '17:00', 30, 0), -- Thu
    ('11111111-1111-1111-1111-111111111111', 5, '09:00', '17:00', 30, 0); -- Fri

-- Dr. Priya Sharma (Dermatologist)
-- Available Monday, Wednesday, Friday, 10:00 to 14:00, 20 min slots, 10 min break
INSERT INTO doctor_availability (doctor_id, day_of_week, start_time, end_time, slot_duration, break_duration) VALUES
    ('22222222-2222-2222-2222-222222222222', 1, '10:00', '14:00', 20, 10), -- Mon
    ('22222222-2222-2222-2222-222222222222', 3, '10:00', '14:00', 20, 10), -- Wed
    ('22222222-2222-2222-2222-222222222222', 5, '10:00', '14:00', 20, 10); -- Fri

-- Dr. Rahul Verma (Cardiologist)
-- Available Tuesday, Thursday, 14:00 to 19:00, 30 min slots, 15 min break
INSERT INTO doctor_availability (doctor_id, day_of_week, start_time, end_time, slot_duration, break_duration) VALUES
    ('33333333-3333-3333-3333-333333333333', 2, '14:00', '19:00', 30, 15), -- Tue
    ('33333333-3333-3333-3333-333333333333', 4, '14:00', '19:00', 30, 15); -- Thu

-- Dr. Ananya Desai (Pediatrician)
-- Available Weekends (Saturday & Sunday), 09:00 to 13:00, 30 min slots, 5 min break
INSERT INTO doctor_availability (doctor_id, day_of_week, start_time, end_time, slot_duration, break_duration) VALUES
    ('44444444-4444-4444-4444-444444444444', 6, '09:00', '13:00', 30, 5), -- Sat
    ('44444444-4444-4444-4444-444444444444', 0, '09:00', '13:00', 30, 5); -- Sun


-- =====================================================
-- POPULATE DOCTOR UNAVAILABILITY (Holidays / Leaves)
-- =====================================================
-- Using dynamic dates based on CURRENT_DATE so the test data is always in the future

-- Dr. Arjun is on a full day leave 3 days from now
INSERT INTO doctor_unavailability (doctor_id, unavailable_date, start_time, end_time, reason)
VALUES
    ('11111111-1111-1111-1111-111111111111', CURRENT_DATE + INTERVAL '3 days', NULL, NULL, 'Annual Leave');

-- Dr. Priya is away for a medical conference for half a day, 5 days from now
INSERT INTO doctor_unavailability (doctor_id, unavailable_date, start_time, end_time, reason)
VALUES
    ('22222222-2222-2222-2222-222222222222', CURRENT_DATE + INTERVAL '5 days', '10:00', '12:00', 'Attending Medical Conference');

-- Dr. Rahul is on a full week leave starting next week
INSERT INTO doctor_unavailability (doctor_id, unavailable_date, start_time, end_time, reason)
VALUES
    ('33333333-3333-3333-3333-333333333333', CURRENT_DATE + INTERVAL '7 days', NULL, NULL, 'Family Vacation'),
    ('33333333-3333-3333-3333-333333333333', CURRENT_DATE + INTERVAL '8 days', NULL, NULL, 'Family Vacation');
