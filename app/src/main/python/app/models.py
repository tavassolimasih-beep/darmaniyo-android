import enum
import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Date, Time, Text,
    ForeignKey, Enum, Numeric, UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.database import Base


class UserRole(str, enum.Enum):
    admin = "admin"          # مدیر سیستم
    doctor = "doctor"        # پزشک
    secretary = "secretary"  # منشی / پذیرش
    accountant = "accountant"  # حسابدار / بخش مالی
    nurse = "nurse"          # پرستار


class AppointmentStatus(str, enum.Enum):
    pending = "pending"      # در انتظار
    confirmed = "confirmed"  # تایید شده
    done = "done"            # انجام شده
    canceled = "canceled"    # لغو شده


class LabTestStatus(str, enum.Enum):
    pending = "pending"  # در انتظار جواب
    done = "done"        # جواب آماده است


class TestWorkflowStatus(str, enum.Enum):
    requested = "requested"  # توسط پزشک درخواست شده
    paid = "paid"            # هزینه پرداخت شده و آماده انجام
    in_progress = "in_progress"  # در حال انجام
    done = "done"            # تست انجام شده
    canceled = "canceled"    # لغو شده


class InvoiceStatus(str, enum.Enum):
    unpaid = "unpaid"
    partial = "partial"
    paid = "paid"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(150), nullable=False)
    username = Column(String(80), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.secretary)
    phone = Column(String(20), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    appointments = relationship("Appointment", back_populates="doctor")
    prescriptions = relationship("Prescription", back_populates="doctor")



class InsuranceCompany(Base):
    """شرکت/سازمان بیمه طرف قرارداد کلینیک و درصد تعهد آن."""
    __tablename__ = "insurance_companies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), unique=True, nullable=False)
    coverage_percent = Column(Numeric(5, 2), nullable=False, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    patients = relationship("Patient", back_populates="insurance")
    invoices = relationship("Invoice", back_populates="insurance")
    service_coverages = relationship("InsuranceServiceCoverage", back_populates="insurance", cascade="all, delete-orphan")


class InsuranceServiceCoverage(Base):
    """درصد تعهد هر بیمه برای هر خدمت. نبودن رکورد یعنی خدمت تحت پوشش نیست."""
    __tablename__ = "insurance_service_coverages"

    id = Column(Integer, primary_key=True, index=True)
    insurance_id = Column(Integer, ForeignKey("insurance_companies.id", ondelete="CASCADE"), nullable=False, index=True)
    service_item_id = Column(Integer, ForeignKey("service_items.id", ondelete="CASCADE"), nullable=False, index=True)
    coverage_percent = Column(Numeric(5, 2), nullable=False, default=0)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    insurance = relationship("InsuranceCompany", back_populates="service_coverages")
    service_item = relationship("ServiceItem", back_populates="insurance_coverages")

    __table_args__ = (UniqueConstraint("insurance_id", "service_item_id", name="UQ_insurance_service_coverage"),)



class PrescriptionStatus(str, enum.Enum):
    draft = "draft"
    pending = "pending"
    submitted = "submitted"
    accepted = "accepted"
    rejected = "rejected"
    cancelled = "cancelled"


class TransmissionStatus(str, enum.Enum):
    pending = "pending"
    submitted = "submitted"
    accepted = "accepted"
    rejected = "rejected"
    failed = "failed"


class InsuranceProvider(Base):
    """بیمه‌گر مستقل از قراردادهای مالی کلینیک؛ برای اتصال آینده به API رسمی."""
    __tablename__ = "insurance_providers"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    patients = relationship("InsurancePatient", back_populates="provider", cascade="all, delete-orphan")
    prescriptions = relationship("Prescription", back_populates="provider")
    configs = relationship("InsuranceProviderConfig", back_populates="provider", cascade="all, delete-orphan")
    transmissions = relationship("PrescriptionTransmission", back_populates="provider")


class InsurancePatient(Base):
    __tablename__ = "insurance_patients"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    provider_id = Column(Integer, ForeignKey("insurance_providers.id"), nullable=False, index=True)
    insurance_number = Column(String(100), nullable=True)
    national_code = Column(String(20), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    patient = relationship("Patient", back_populates="insurance_profiles")
    provider = relationship("InsuranceProvider", back_populates="patients")
    __table_args__ = (UniqueConstraint("patient_id", "provider_id", name="UQ_insurance_patient_provider"),)


class InsuranceProviderConfig(Base):
    __tablename__ = "insurance_provider_configs"

    id = Column(Integer, primary_key=True, index=True)
    provider_id = Column(Integer, ForeignKey("insurance_providers.id", ondelete="CASCADE"), nullable=False, index=True)
    environment = Column(String(20), nullable=False, default="test")
    base_url = Column(String(500), nullable=True)
    enabled = Column(Boolean, default=False, nullable=False)
    client_id = Column(String(255), nullable=True)
    client_secret = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    provider = relationship("InsuranceProvider", back_populates="configs")


class Drug(Base):
    """داروی استاندارد برای نسخه‌نویسی؛ مستقل از لیست داروهای مصرفی پرستاری."""
    __tablename__ = "drugs"

    id = Column(Integer, primary_key=True, index=True)
    national_drug_code = Column(String(100), nullable=True, index=True)
    generic_name = Column(String(250), nullable=False)
    brand_name = Column(String(250), nullable=True)
    dosage_form = Column(String(100), nullable=True)
    strength = Column(String(100), nullable=True)
    unit = Column(String(50), nullable=True)
    manufacturer = Column(String(200), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    prescription_items = relationship("PrescriptionItem", back_populates="drug")


class Prescription(Base):
    __tablename__ = "prescriptions"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    doctor_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    provider_id = Column(Integer, ForeignKey("insurance_providers.id"), nullable=True, index=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), nullable=True, index=True)
    prescription_date = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    status = Column(Enum(PrescriptionStatus), default=PrescriptionStatus.draft, nullable=False)
    external_prescription_id = Column(String(200), nullable=True)
    tracking_code = Column(String(200), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    patient = relationship("Patient", back_populates="prescriptions")
    doctor = relationship("User", back_populates="prescriptions")
    provider = relationship("InsuranceProvider", back_populates="prescriptions")
    appointment = relationship("Appointment")
    items = relationship("PrescriptionItem", back_populates="prescription", cascade="all, delete-orphan")
    transmissions = relationship("PrescriptionTransmission", back_populates="prescription", cascade="all, delete-orphan")


class PrescriptionItem(Base):
    __tablename__ = "prescription_items"

    id = Column(Integer, primary_key=True, index=True)
    prescription_id = Column(Integer, ForeignKey("prescriptions.id", ondelete="CASCADE"), nullable=False, index=True)
    drug_id = Column(Integer, ForeignKey("drugs.id"), nullable=True, index=True)
    medication_id = Column(Integer, ForeignKey("medications.id"), nullable=True, index=True)
    drug_name = Column(String(250), nullable=False)
    national_drug_code = Column(String(100), nullable=True)
    dosage = Column(String(150), nullable=True)
    frequency = Column(String(150), nullable=True)
    duration = Column(String(100), nullable=True)
    route = Column(String(100), nullable=True)
    instructions = Column(Text, nullable=True)
    quantity = Column(Integer, nullable=True)

    prescription = relationship("Prescription", back_populates="items")
    drug = relationship("Drug", back_populates="prescription_items")
    medication = relationship("Medication")


class PrescriptionTransmission(Base):
    __tablename__ = "prescription_transmissions"

    id = Column(Integer, primary_key=True, index=True)
    prescription_id = Column(Integer, ForeignKey("prescriptions.id", ondelete="CASCADE"), nullable=False, index=True)
    provider_id = Column(Integer, ForeignKey("insurance_providers.id"), nullable=False, index=True)
    status = Column(Enum(TransmissionStatus), default=TransmissionStatus.pending, nullable=False)
    external_prescription_id = Column(String(200), nullable=True)
    tracking_code = Column(String(200), nullable=True)
    request_id = Column(String(200), nullable=True)
    response_code = Column(String(100), nullable=True)
    response_message = Column(Text, nullable=True)
    request_body = Column(Text, nullable=True)
    response_body = Column(Text, nullable=True)
    submitted_at = Column(DateTime, nullable=True)
    last_attempt_at = Column(DateTime, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    prescription = relationship("Prescription", back_populates="transmissions")
    provider = relationship("InsuranceProvider", back_populates="transmissions")


class InsuranceApiLog(Base):
    __tablename__ = "insurance_api_logs"

    id = Column(Integer, primary_key=True, index=True)
    provider_id = Column(Integer, ForeignKey("insurance_providers.id"), nullable=True, index=True)
    prescription_id = Column(Integer, ForeignKey("prescriptions.id"), nullable=True, index=True)
    operation = Column(String(100), nullable=False)
    http_status = Column(Integer, nullable=True)
    request_body = Column(Text, nullable=True)
    response_body = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class Patient(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(150), nullable=False)
    national_code = Column(String(20), unique=True, index=True, nullable=True)
    phone = Column(String(20), nullable=True)
    birth_date = Column(Date, nullable=True)
    gender = Column(String(10), nullable=True)  # مرد / زن
    address = Column(Text, nullable=True)
    medical_notes = Column(Text, nullable=True)  # سوابق پزشکی / حساسیت‌ها
    insurance_id = Column(Integer, ForeignKey("insurance_companies.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    appointments = relationship("Appointment", back_populates="patient", cascade="all, delete-orphan")
    lab_tests = relationship("LabTest", back_populates="patient", cascade="all, delete-orphan")
    invoices = relationship("Invoice", back_populates="patient", cascade="all, delete-orphan")
    insurance = relationship("InsuranceCompany", back_populates="patients")
    insurance_profiles = relationship("InsurancePatient", back_populates="patient", cascade="all, delete-orphan")
    prescriptions = relationship("Prescription", back_populates="patient", cascade="all, delete-orphan")


class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    doctor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    appointment_date = Column(Date, nullable=False)
    appointment_time = Column(Time, nullable=False)
    reason = Column(String(255), nullable=True)
    status = Column(Enum(AppointmentStatus), default=AppointmentStatus.pending)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    patient = relationship("Patient", back_populates="appointments")
    doctor = relationship("User", back_populates="appointments")
    vitals = relationship(
        "Vitals", back_populates="appointment", uselist=False, cascade="all, delete-orphan"
    )


class LabTest(Base):
    __tablename__ = "lab_tests"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    test_name = Column(String(200), nullable=False)
    ordered_at = Column(DateTime, default=datetime.datetime.utcnow)
    status = Column(Enum(LabTestStatus), default=LabTestStatus.pending)
    result_text = Column(Text, nullable=True)
    result_file = Column(String(255), nullable=True)  # مسیر فایل ضمیمه (مثلا PDF/عکس)

    # ارتباط تست با نوبتی که پزشک در آن درخواست کرده است
    appointment_id = Column(Integer, ForeignKey("appointments.id"), nullable=True, index=True)
    ordered_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    service_item_id = Column(Integer, ForeignKey("service_items.id"), nullable=True)
    price = Column(Numeric(12, 0), default=0)
    workflow_status = Column(Enum(TestWorkflowStatus), default=TestWorkflowStatus.requested, nullable=False)

    patient = relationship("Patient", back_populates="lab_tests")
    appointment = relationship("Appointment")
    ordered_by = relationship("User")
    service_item = relationship("ServiceItem")
    invoice_item = relationship("InvoiceItem", back_populates="lab_test", uselist=False)


class ServiceItem(Base):
    """آیتم‌های خدمات مالی قابل انتخاب (نوار قلب، اکو قلب و ...) — به‌جای Hard-Code در کد،
    از یک جدول مستقل خوانده می‌شوند تا بتوان بدون تغییر کد، آیتم جدید اضافه/ویرایش/غیرفعال کرد."""

    __tablename__ = "service_items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), unique=True, nullable=False)
    default_price = Column(Numeric(12, 0), nullable=True)  # قیمت پیش‌فرض (اختیاری)
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    insurance_coverages = relationship("InsuranceServiceCoverage", back_populates="service_item", cascade="all, delete-orphan")


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    total_amount = Column(Numeric(12, 0), default=0)
    discount = Column(Numeric(12, 0), default=0)
    insurance_id = Column(Integer, ForeignKey("insurance_companies.id"), nullable=True, index=True)
    insurance_percent = Column(Numeric(5, 2), nullable=False, default=0)
    insurance_amount = Column(Numeric(12, 0), nullable=False, default=0)
    patient_payable = Column(Numeric(12, 0), nullable=False, default=0)
    status = Column(Enum(InvoiceStatus), default=InvoiceStatus.unpaid)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    patient = relationship("Patient", back_populates="invoices")
    items = relationship("InvoiceItem", back_populates="invoice", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="invoice", cascade="all, delete-orphan")
    insurance = relationship("InsuranceCompany", back_populates="invoices")

    @property
    def paid_amount(self):
        return sum(p.amount for p in self.payments)

    @property
    def remaining_amount(self):
        return max(0.0, float(self.patient_payable) - float(self.paid_amount))


class InvoiceItem(Base):
    __tablename__ = "invoice_items"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False)
    description = Column(String(255), nullable=False)
    amount = Column(Numeric(12, 0), nullable=False)
    lab_test_id = Column(Integer, ForeignKey("lab_tests.id"), nullable=True)
    service_item_id = Column(Integer, ForeignKey("service_items.id"), nullable=True, index=True)

    invoice = relationship("Invoice", back_populates="items")
    lab_test = relationship("LabTest", back_populates="invoice_item")
    service_item = relationship("ServiceItem")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False)
    amount = Column(Numeric(12, 0), nullable=False)
    method = Column(String(30), default="cash")  # cash / card / online
    paid_at = Column(DateTime, default=datetime.datetime.utcnow)

    invoice = relationship("Invoice", back_populates="payments")


class Medication(Base):
    """لیست داروهای قابل انتخاب برای ثبت داروهای مصرفی بیمار توسط پرستار — این لیست
    هم مانند آیتم‌های مالی در یک جدول مستقل نگهداری می‌شود (نه Hard-Code) تا از صفحه‌ی
    «لیست داروها» قابل افزودن/ویرایش/غیرفعال‌سازی باشد."""

    __tablename__ = "medications"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), unique=True, nullable=False)
    # دوزهای رایج این دارو، جدا شده با کاما، مثلاً: "2.5, 5, 10" — اگر خالی باشد،
    # هنگام ثبت ویزیت به‌جای لیست کشویی، یک کادر متنی برای وارد کردن دوز نمایش داده می‌شود.
    dosage_options = Column(String(300), nullable=True)
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    @property
    def dose_option_list(self):
        if not self.dosage_options:
            return []
        return [d.strip() for d in self.dosage_options.split(",") if d.strip()]


class Vitals(Base):
    """علائم حیاتی و اطلاعات پرستاری ثبت‌شده برای یک نوبت مشخص در «برنامه امروز»:
    فشار خون، اکسیژن خون، ریپورت ECG، سنجش ABI (عروق اندامی) و داروهای مصرفی بیمار.
    هر نوبت حداکثر یک رکورد Vitals دارد و این رکورد کاملاً قابل ویرایش است."""

    __tablename__ = "vitals"

    id = Column(Integer, primary_key=True, index=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), unique=True, nullable=False)

    bp_systolic = Column(Integer, nullable=True)   # فشار خون سیستولیک
    bp_diastolic = Column(Integer, nullable=True)  # فشار خون دیاستولیک
    o2_saturation = Column(Integer, nullable=True)  # درصد اشباع اکسیژن خون

    # گزارش ECG: چون دستگاه ECG مستقیماً به نرم‌افزار این سایت متصل نمی‌شود (این محدودیت
    # هر سامانه‌ی تحت وب است و نیاز به درایور/نرم‌افزار اختصاصی دستگاه دارد)، پرستار می‌تواند
    # خلاصه/تفسیر ریتم را تایپ کند و در صورت نیاز، فایل خروجی دستگاه (عکس/PDF) را ضمیمه کند.
    ecg_notes = Column(Text, nullable=True)
    ecg_file = Column(String(255), nullable=True)
    patient_history = Column(Text, nullable=True)  # شرح حال ثبت‌شده توسط پرستار

    # ABI = Ankle-Brachial Index (شاخص مچ‌پا-بازو برای بررسی عروق اندام‌ها)
    # با ثبت فشار سیستولیک بازو و مچ‌پا برای هر سمت، مقدار ABI به‌صورت خودکار محاسبه می‌شود.
    abi_right_arm = Column(Numeric(6, 1), nullable=True)
    abi_right_ankle = Column(Numeric(6, 1), nullable=True)
    abi_left_arm = Column(Numeric(6, 1), nullable=True)
    abi_left_ankle = Column(Numeric(6, 1), nullable=True)

    recorded_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    recorded_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    appointment = relationship("Appointment", back_populates="vitals")
    recorded_by = relationship("User")
    medications = relationship(
        "VitalMedication", back_populates="vitals", cascade="all, delete-orphan"
    )

    @property
    def abi_right(self):
        if self.abi_right_arm and self.abi_right_ankle:
            try:
                return round(float(self.abi_right_ankle) / float(self.abi_right_arm), 2)
            except (ZeroDivisionError, TypeError):
                return None
        return None

    @property
    def abi_left(self):
        if self.abi_left_arm and self.abi_left_ankle:
            try:
                return round(float(self.abi_left_ankle) / float(self.abi_left_arm), 2)
            except (ZeroDivisionError, TypeError):
                return None
        return None


class VitalMedication(Base):
    """یک قلم دارویی که پرستار برای یک ویزیت مشخص ثبت کرده (نام دارو + دوز انتخابی).
    medication_id ممکن است خالی باشد (وقتی دارو از بیرون لیست اصلی، یعنی «سایر»، وارد شده)."""

    __tablename__ = "vital_medications"

    id = Column(Integer, primary_key=True, index=True)
    vitals_id = Column(Integer, ForeignKey("vitals.id"), nullable=False)
    medication_id = Column(Integer, ForeignKey("medications.id"), nullable=True)
    medication_name = Column(String(200), nullable=False)
    dose = Column(String(100), nullable=True)

    vitals = relationship("Vitals", back_populates="medications")
    medication = relationship("Medication")



class BookingSettings(Base):
    """تنظیمات نوبت آنلاین — یک ردیف فعال برای کل سیستم."""
    __tablename__ = "booking_settings"

    id = Column(Integer, primary_key=True, index=True)
    morning_start = Column(String(5), nullable=False, default="09:00")  # HH:MM
    morning_end = Column(String(5), nullable=False, default="13:00")
    evening_start = Column(String(5), nullable=False, default="16:00")
    evening_end = Column(String(5), nullable=False, default="19:00")
    slot_minutes = Column(Integer, nullable=False, default=30)
    # روزهای تعطیل با کاما: 0=دوشنبه ... 6=یکشنبه (پایتون weekday)
    closed_weekdays = Column(String(50), nullable=False, default="4")  # جمعه
    days_ahead = Column(Integer, nullable=False, default=21)
    clinic_name = Column(String(300), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
