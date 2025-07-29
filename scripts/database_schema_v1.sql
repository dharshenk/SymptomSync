-- =====================================================
-- Symptom Sync Simplified Database Schema
-- PostgreSQL Database Design for AI-Assisted Healthcare
-- =====================================================

-- Enable UUID extension for primary keys
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =====================================================
-- PATIENT MANAGEMENT
-- =====================================================

-- Patient details
CREATE TABLE patients (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id VARCHAR(20) UNIQUE NOT NULL, -- human-readable patient ID like PAT-001
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE,
    phone_number VARCHAR(20) UNIQUE NOT NULL,
    whatsapp_number VARCHAR(20), -- for bot communication
    date_of_birth DATE,
    gender VARCHAR(20) CHECK (gender IN ('male', 'female', 'other', 'prefer_not_to_say')),
    emergency_contact_name VARCHAR(100),
    emergency_contact_phone VARCHAR(20),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- DOCTOR MANAGEMENT
-- =====================================================

-- Doctor details
CREATE TABLE doctors (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    doctor_id VARCHAR(20) UNIQUE NOT NULL, -- human-readable doctor ID like DOC-001
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    phone_number VARCHAR(20) UNIQUE NOT NULL,
    license_number VARCHAR(50) UNIQUE NOT NULL,
    specialization VARCHAR(100) NOT NULL,
    years_experience INTEGER,
    qualification VARCHAR(200),
    hospital_affiliation VARCHAR(200),
    consultation_fee DECIMAL(10,2),
    consultation_duration INTEGER DEFAULT 30, -- in minutes
    bio TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- DOCTOR AVAILABILITY
-- =====================================================

-- Doctor's weekly availability schedule
CREATE TABLE doctor_availability (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    doctor_id UUID REFERENCES doctors(id) ON DELETE CASCADE,
    day_of_week INTEGER CHECK (day_of_week BETWEEN 0 AND 6), -- 0=Sunday, 6=Saturday
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    slot_duration INTEGER DEFAULT 30, -- minutes per appointment slot
    break_duration INTEGER DEFAULT 15, -- minutes between appointments
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Doctor unavailability (holidays, leaves, specific dates)
CREATE TABLE doctor_unavailability (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    doctor_id UUID REFERENCES doctors(id) ON DELETE CASCADE,
    unavailable_date DATE NOT NULL,
    start_time TIME, -- NULL means entire day unavailable
    end_time TIME,   -- NULL means entire day unavailable
    reason VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- CHAT SESSION MANAGEMENT
-- =====================================================

-- AI bot conversation sessions with patients
CREATE TABLE chat_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id VARCHAR(50) UNIQUE NOT NULL, -- external session identifier
    patient_id UUID REFERENCES patients(id) ON DELETE CASCADE,
    session_status VARCHAR(20) DEFAULT 'active' CHECK (session_status IN ('active', 'completed', 'abandoned')),
    started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE,
    total_messages INTEGER DEFAULT 0,
    session_summary TEXT, -- AI-generated summary of the conversation
    appointment_requested BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Individual messages within chat sessions
CREATE TABLE chat_messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID REFERENCES chat_sessions(id) ON DELETE CASCADE,
    message_sequence INTEGER NOT NULL, -- order of messages in session
    sender_type VARCHAR(10) NOT NULL CHECK (sender_type IN ('patient', 'bot')),
    message_content TEXT NOT NULL,
    message_type VARCHAR(20) DEFAULT 'text' CHECK (message_type IN ('text', 'quick_reply', 'image', 'document', 'location')),
    metadata JSONB, -- store additional message data like attachments, coordinates, etc.
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(session_id, message_sequence)
);
    -- Ensure message ordering within session

-- =====================================================
-- APPOINTMENT MANAGEMENT
-- =====================================================

-- Appointments between patients and doctors
CREATE TABLE appointments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    appointment_number VARCHAR(20) UNIQUE NOT NULL, -- human-readable like APT-001
    patient_id UUID REFERENCES patients(id) ON DELETE CASCADE,
    doctor_id UUID REFERENCES doctors(id) ON DELETE CASCADE,
    chat_session_id UUID REFERENCES chat_sessions(id), -- link to originating chat session
    appointment_date DATE NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    appointment_type VARCHAR(30) DEFAULT 'consultation' CHECK (
        appointment_type IN ('consultation', 'follow_up', 'emergency', 'telemedicine')
    ),
    status VARCHAR(20) DEFAULT 'scheduled' CHECK (
        status IN ('scheduled', 'confirmed', 'in_progress', 'completed', 'cancelled', 'no_show', 'rescheduled')
    ),
    consultation_fee DECIMAL(10,2),
    payment_status VARCHAR(20) DEFAULT 'pending' CHECK (
        payment_status IN ('pending', 'paid', 'refunded', 'cancelled')
    ),
    cancellation_reason TEXT,
    rescheduled_from_id UUID REFERENCES appointments(id), -- if this appointment is a reschedule
    patient_notes TEXT, -- notes from the chat session
    doctor_notes TEXT, -- notes added by doctor after consultation
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- SYSTEM CONFIGURATION
-- =====================================================

-- System-wide configuration settings
CREATE TABLE system_config (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    config_key VARCHAR(100) UNIQUE NOT NULL,
    config_value TEXT,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- INDEXES FOR PERFORMANCE
-- =====================================================

-- Patient indexes
CREATE INDEX idx_patients_email ON patients(email);
CREATE INDEX idx_patients_phone ON patients(phone_number);
CREATE INDEX idx_patients_patient_id ON patients(patient_id);
CREATE INDEX idx_patients_active ON patients(is_active);

-- Doctor indexes
CREATE INDEX idx_doctors_email ON doctors(email);
CREATE INDEX idx_doctors_doctor_id ON doctors(doctor_id);
CREATE INDEX idx_doctors_specialization ON doctors(specialization);
CREATE INDEX idx_doctors_active ON doctors(is_active);

-- Doctor availability indexes
CREATE INDEX idx_doctor_availability_doctor ON doctor_availability(doctor_id);
CREATE INDEX idx_doctor_availability_day ON doctor_availability(day_of_week);
CREATE INDEX idx_doctor_availability_active ON doctor_availability(is_active);
CREATE INDEX idx_doctor_unavailability_doctor_date ON doctor_unavailability(doctor_id, unavailable_date);

-- Chat session indexes
CREATE INDEX idx_chat_sessions_patient ON chat_sessions(patient_id);
CREATE INDEX idx_chat_sessions_status ON chat_sessions(session_status);
CREATE INDEX idx_chat_sessions_started ON chat_sessions(started_at);
CREATE INDEX idx_chat_sessions_session_id ON chat_sessions(session_id);

-- Chat message indexes
CREATE INDEX idx_chat_messages_session ON chat_messages(session_id);
CREATE INDEX idx_chat_messages_timestamp ON chat_messages(timestamp);
CREATE INDEX idx_chat_messages_sequence ON chat_messages(session_id, message_sequence);

-- Appointment indexes
CREATE INDEX idx_appointments_patient ON appointments(patient_id);
CREATE INDEX idx_appointments_doctor ON appointments(doctor_id);
CREATE INDEX idx_appointments_date ON appointments(appointment_date);
CREATE INDEX idx_appointments_status ON appointments(status);
CREATE INDEX idx_appointments_number ON appointments(appointment_number);
CREATE INDEX idx_appointments_chat_session ON appointments(chat_session_id);

-- =====================================================
-- TRIGGERS FOR AUTO-UPDATE TIMESTAMPS
-- =====================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply triggers to tables with updated_at columns
CREATE TRIGGER update_patients_updated_at BEFORE UPDATE ON patients
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_doctors_updated_at BEFORE UPDATE ON doctors
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_doctor_availability_updated_at BEFORE UPDATE ON doctor_availability
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_appointments_updated_at BEFORE UPDATE ON appointments
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_system_config_updated_at BEFORE UPDATE ON system_config
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =====================================================
-- TRIGGERS FOR BUSINESS LOGIC
-- =====================================================

-- Function to update total_messages count in chat_sessions
CREATE OR REPLACE FUNCTION update_session_message_count()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE chat_sessions
        SET total_messages = total_messages + 1
        WHERE id = NEW.session_id;
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE chat_sessions
        SET total_messages = total_messages - 1
        WHERE id = OLD.session_id;
        RETURN OLD;
    END IF;
    RETURN NULL;
END;
$$ language 'plpgsql';

-- Trigger to maintain message count
CREATE TRIGGER update_chat_session_message_count
    AFTER INSERT OR DELETE ON chat_messages
    FOR EACH ROW EXECUTE FUNCTION update_session_message_count();

-- =====================================================
-- USEFUL VIEWS
-- =====================================================

-- Available appointment slots for a doctor on a specific date
CREATE OR REPLACE FUNCTION get_available_slots(
    p_doctor_id UUID,
    p_appointment_date DATE
) RETURNS TABLE (
    slot_start TIME,
    slot_end TIME
) AS $$
DECLARE
    availability_rec RECORD;
    slot_start_time TIME;
    slot_end_time TIME;
    slot_duration INTERVAL;
BEGIN
    -- Get doctor's availability for the day of week
    SELECT da.start_time, da.end_time,
           MAKE_INTERVAL(mins => da.slot_duration) as duration,
           MAKE_INTERVAL(mins => da.break_duration) as break_time
    INTO availability_rec
    FROM doctor_availability da
    WHERE da.doctor_id = p_doctor_id
      AND da.day_of_week = EXTRACT(DOW FROM p_appointment_date)
      AND da.is_active = true;

    -- If no availability found, return empty
    IF NOT FOUND THEN
        RETURN;
    END IF;

    -- Check if doctor is unavailable on this specific date
    IF EXISTS (
        SELECT 1 FROM doctor_unavailability du
        WHERE du.doctor_id = p_doctor_id
          AND du.unavailable_date = p_appointment_date
          AND du.start_time IS NULL -- entire day unavailable
    ) THEN
        RETURN;
    END IF;

    -- Generate time slots
    slot_start_time := availability_rec.start_time;
    slot_duration := availability_rec.duration;

    WHILE slot_start_time + slot_duration <= availability_rec.end_time LOOP
        slot_end_time := slot_start_time + slot_duration;

        -- Check if slot is not already booked
        IF NOT EXISTS (
            SELECT 1 FROM appointments a
            WHERE a.doctor_id = p_doctor_id
              AND a.appointment_date = p_appointment_date
              AND a.start_time = slot_start_time
              AND a.status NOT IN ('cancelled', 'no_show')
        ) THEN
            -- Check if slot is not in unavailable time range
            IF NOT EXISTS (
                SELECT 1 FROM doctor_unavailability du
                WHERE du.doctor_id = p_doctor_id
                  AND du.unavailable_date = p_appointment_date
                  AND du.start_time IS NOT NULL
                  AND slot_start_time >= du.start_time
                  AND slot_end_time <= du.end_time
            ) THEN
                slot_start := slot_start_time;
                slot_end := slot_end_time;
                RETURN NEXT;
            END IF;
        END IF;

        slot_start_time := slot_start_time + slot_duration + availability_rec.break_time;
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- SAMPLE DATA
-- =====================================================

-- Insert sample system configurations
INSERT INTO system_config (config_key, config_value, description) VALUES
('max_appointment_days_ahead', '30', 'Maximum days ahead patients can book appointments'),
('min_appointment_notice_hours', '2', 'Minimum hours notice required for booking'),
('default_session_timeout_hours', '24', 'Hours before inactive chat session expires'),
('whatsapp_webhook_secret', 'your_webhook_secret_here', 'WhatsApp webhook verification secret');

-- =====================================================
-- TABLE COMMENTS
-- =====================================================

COMMENT ON TABLE patients IS 'Patient information and contact details';
COMMENT ON TABLE doctors IS 'Doctor profiles and professional information';
COMMENT ON TABLE doctor_availability IS 'Weekly schedule templates for doctors';
COMMENT ON TABLE doctor_unavailability IS 'Specific dates/times when doctors are not available';
COMMENT ON TABLE chat_sessions IS 'AI bot conversation sessions with patients';
COMMENT ON TABLE chat_messages IS 'Individual messages within chat sessions';
COMMENT ON TABLE appointments IS 'Scheduled appointments between patients and doctors';
COMMENT ON TABLE system_config IS 'Application-wide configuration settings';

COMMENT ON FUNCTION get_available_slots(UUID, DATE) IS 'Returns available appointment slots for a doctor on a specific date';
