"""A terminal school management program with CSV persistence.

Run with ``python main.py``. No third-party packages are required.
"""

import csv
import math
import os
from datetime import date
from pathlib import Path
import sys
import tempfile


DATA_DIRECTORY = Path(__file__).resolve().parent / "data"
SCHEMAS = {
    "students": ("student_id", "first_name", "last_name", "class_id"),
    "teachers": ("teacher_id", "first_name", "last_name"),
    "classes": ("class_id", "name"),
    "subjects": ("subject_id", "name", "teacher_id"),
    "grades": ("student_id", "subject_id", "score"),
    "attendance": ("student_id", "date", "status"),
}
RECORD_KEYS = {
    "students": ("student_id",),
    "teachers": ("teacher_id",),
    "classes": ("class_id",),
    "subjects": ("subject_id",),
    "grades": ("student_id", "subject_id"),
    "attendance": ("student_id", "date"),
}
OPTIONAL_FIELDS = {("students", "class_id"), ("subjects", "teacher_id")}
LABELS = {
    "students": "Student",
    "teachers": "Teacher",
    "classes": "Class",
    "subjects": "Subject",
}
ATTENDANCE_STATUSES = ("Present", "Absent", "Late", "Excused")


def valid_score(value):
    """Return a finite score from 0 to 100, or explain the invalid input."""
    try:
        score = float(value)
    except ValueError:
        raise ValueError("Grade must be a number from 0 to 100.") from None
    if not math.isfinite(score) or not 0 <= score <= 100:
        raise ValueError("Grade must be a number from 0 to 100.")
    return score


def valid_date(value):
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValueError("Date must be a real date in YYYY-MM-DD format.") from None
    if parsed.isoformat() != value:
        raise ValueError("Date must be a real date in YYYY-MM-DD format.")
    return value


class CSVStorage:
    """Load records at startup and save every change before reporting success."""

    def __init__(self, directory=DATA_DIRECTORY):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._records = {}
        for table, fields in SCHEMAS.items():
            path = self.directory / f"{table}.csv"
            if not path.exists():
                self._records[table] = []
                continue
            try:
                with path.open("r", encoding="utf-8-sig", newline="") as handle:
                    reader = csv.DictReader(handle, strict=True)
                    if reader.fieldnames != list(fields):
                        raise ValueError(f"{path.name}: expected columns {', '.join(fields)}.")
                    records = list(reader)
            except csv.Error as error:
                raise ValueError(f"{path.name}: invalid CSV: {error}") from error
            self._validate_rows(table, records)
            self._records[table] = records

        self._validate_relationships()
        # Create missing files only after existing data has passed validation.
        for table in SCHEMAS:
            if not (self.directory / f"{table}.csv").exists():
                self.save(table, [])

    @staticmethod
    def _validate_rows(table, records):
        seen = set()
        for line, record in enumerate(records, start=2):
            if set(record) != set(SCHEMAS[table]) or any(
                value is None for value in record.values()
            ):
                raise ValueError(f"{table}.csv, row {line}: incorrect number of fields.")
            for field, value in record.items():
                if not value.strip() and (table, field) not in OPTIONAL_FIELDS:
                    raise ValueError(f"{table}.csv, row {line}: {field} is required.")
                if value != value.strip():
                    raise ValueError(f"{table}.csv, row {line}: trim spaces around {field}.")
            key = tuple(record[field] for field in RECORD_KEYS[table])
            if key in seen:
                raise ValueError(f"{table}.csv, row {line}: duplicate record ID/key.")
            seen.add(key)

    def _validate_relationships(self):
        ids = {
            table: {row[SCHEMAS[table][0]] for row in self._records[table]}
            for table in LABELS
        }
        links = (
            ("students", "class_id", "classes"),
            ("subjects", "teacher_id", "teachers"),
            ("grades", "student_id", "students"),
            ("grades", "subject_id", "subjects"),
            ("attendance", "student_id", "students"),
        )
        for table, field, target in links:
            for record in self._records[table]:
                value = record[field]
                if value and value not in ids[target]:
                    raise ValueError(f"{table}.csv: unknown {field} '{value}'.")
        for record in self._records["grades"]:
            valid_score(record["score"])
        for record in self._records["attendance"]:
            valid_date(record["date"])
            if record["status"] not in ATTENDANCE_STATUSES:
                raise ValueError("attendance.csv: invalid attendance status.")

    def rows(self, table):
        # Callers edit copies so failed writes cannot change the loaded data.
        return [row.copy() for row in self._records[table]]

    def find(self, table, record_id):
        key = SCHEMAS[table][0]
        return next((row for row in self.rows(table) if row[key] == record_id), None)

    def save(self, table, records):
        """Replace a CSV atomically so an interrupted write cannot truncate it."""
        records = [row.copy() for row in records]
        self._validate_rows(table, records)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", newline="", dir=self.directory,
                prefix=f".{table}-", suffix=".tmp", delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                writer = csv.DictWriter(handle, fieldnames=SCHEMAS[table])
                writer.writeheader()
                writer.writerows(records)
                handle.flush()
                os.fsync(handle.fileno())
            temporary_path.replace(self.directory / f"{table}.csv")
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        self._records[table] = records

    def upsert(self, table, record):
        keys = RECORD_KEYS[table]
        records = self.rows(table)
        for index, existing in enumerate(records):
            if all(existing[key] == record[key] for key in keys):
                records[index] = record
                break
        else:
            records.append(record)
        self.save(table, records)


class SchoolManagement:
    def __init__(self, storage):
        self.storage = storage

    @staticmethod
    def required(prompt):
        value = input(f"{prompt}: ").strip()
        if not value:
            raise ValueError(f"{prompt} is required.")
        return value

    def select(self, table):
        label = LABELS[table]
        record_id = self.required(f"{label} ID")
        record = self.storage.find(table, record_id)
        if record is None:
            raise ValueError(f"{label} ID '{record_id}' does not exist.")
        return record

    def new_id(self, table):
        label = LABELS[table]
        record_id = self.required(f"{label} ID")
        if self.storage.find(table, record_id) is not None:
            raise ValueError(f"{label} ID '{record_id}' already exists.")
        return record_id

    @staticmethod
    def display(headers, rows):
        rows = [[str(value) for value in row] for row in rows]
        if not rows:
            print("No records found.")
            return
        widths = [max(len(header), *(len(row[i]) for row in rows))
                  for i, header in enumerate(headers)]
        print(" | ".join(header.ljust(widths[i]) for i, header in enumerate(headers)))
        print("-+-".join("-" * width for width in widths))
        for row in rows:
            print(" | ".join(value.ljust(widths[i]) for i, value in enumerate(row)))

    def menu(self, title, actions, exit_label="Back to Main Menu"):
        while True:
            print(f"\n--- {title} ---")
            for number, (label, _) in enumerate(actions, start=1):
                print(f"{number}: {label}")
            exit_choice = str(len(actions) + 1)
            print(f"{exit_choice}: {exit_label}")
            choice = input("Navigate Menu: ").strip()
            if choice == exit_choice:
                return
            if choice not in {str(i) for i in range(1, len(actions) + 1)}:
                print("Unknown menu option. Choose one of the listed numbers.")
                continue
            try:
                actions[int(choice) - 1][1]()
            except ValueError as error:
                print(f"Error: {error}")
            except OSError as error:
                print(f"Could not save records: {error}")

    def run(self):
        print("School Management")
        print(f"CSV records: {self.storage.directory.resolve()}")
        self.menu("Main Menu", [
            ("Student Management", lambda: self.people_menu("students")),
            ("Teacher Management", lambda: self.people_menu("teachers")),
            ("Class and Subject Management", self.classes_menu),
            ("View / Manage Grades", self.grades_menu),
            ("View / Record Attendance", self.attendance_menu),
            ("Basic Report", self.reports_menu),
        ], exit_label="Exit")
        print("Goodbye. All saved records are in the CSV files.")

    def people_menu(self, table):
        label = LABELS[table]
        self.menu(f"{label} Management", [
            (f"Add {label}", lambda: self.add_person(table)),
            (f"List {table.title()}", lambda: self.list_records(table)),
            (f"Update {label}", lambda: self.update_person(table)),
            (f"Delete {label}", lambda: self.delete_person(table)),
        ])

    def add_person(self, table):
        record = {
            SCHEMAS[table][0]: self.new_id(table),
            "first_name": self.required("First Name"),
            "last_name": self.required("Last Name"),
        }
        if table == "students":
            record["class_id"] = ""
        self.storage.upsert(table, record)
        print(f"{LABELS[table]} added.")

    def list_records(self, table):
        fields = SCHEMAS[table]
        headers = [field.replace("_", " ").title().replace("Id", "ID") for field in fields]
        self.display(headers, [[row[field] for field in fields]
                               for row in self.storage.rows(table)])

    def update_person(self, table):
        record = self.select(table)
        print("Leave a name blank to keep its current value.")
        for field, label in (("first_name", "First Name"), ("last_name", "Last Name")):
            value = input(f"{label} [{record[field]}]: ").strip()
            if value:
                record[field] = value
        self.storage.upsert(table, record)
        print(f"{LABELS[table]} updated.")

    def delete_person(self, table):
        record = self.select(table)
        key = SCHEMAS[table][0]
        record_id = record[key]
        if table == "students":
            detail = " Their grades and attendance will also be deleted."
        else:
            detail = " Their subject assignments will be cleared."
        answer = input(
            f"Delete {record['first_name']} {record['last_name']}?{detail} [y/N]: "
        ).strip().lower()
        if answer not in ("y", "yes"):
            print("Deletion cancelled.")
            return
        # Clear dependent records first to avoid leaving references to a deleted ID.
        if table == "students":
            for related in ("grades", "attendance"):
                self.storage.save(related, [row for row in self.storage.rows(related)
                                            if row["student_id"] != record_id])
        else:
            subjects = self.storage.rows("subjects")
            for subject in subjects:
                if subject["teacher_id"] == record_id:
                    subject["teacher_id"] = ""
            self.storage.save("subjects", subjects)
        self.storage.save(table, [row for row in self.storage.rows(table)
                                  if row[key] != record_id])
        print(f"{LABELS[table]} deleted.")

    def classes_menu(self):
        self.menu("Class and Subject Management", [
            ("Create Class", lambda: self.add_named_record("classes")),
            ("Create Subject", lambda: self.add_named_record("subjects")),
            ("List Classes", lambda: self.list_records("classes")),
            ("List Subjects", lambda: self.list_records("subjects")),
            ("Assign Student to Class", self.assign_student),
            ("Assign Teacher to Subject", self.assign_teacher),
        ])

    def add_named_record(self, table):
        record = {
            SCHEMAS[table][0]: self.new_id(table),
            "name": self.required(f"{LABELS[table]} Name"),
        }
        if table == "subjects":
            record["teacher_id"] = ""
        self.storage.upsert(table, record)
        print(f"{LABELS[table]} created.")

    def assign_student(self):
        student = self.select("students")
        school_class = self.select("classes")
        student["class_id"] = school_class["class_id"]
        self.storage.upsert("students", student)
        print(f"Student assigned to {school_class['name']}.")

    def assign_teacher(self):
        teacher = self.select("teachers")
        subject = self.select("subjects")
        subject["teacher_id"] = teacher["teacher_id"]
        self.storage.upsert("subjects", subject)
        print(f"Teacher assigned to {subject['name']}.")

    def grades_menu(self):
        self.menu("Grades", [
            ("Add / Update a Student Grade", self.add_grade),
            ("Add / Update Multiple Students' Grades", self.add_multiple_grades),
            ("View All Grades", self.view_grades),
            ("View a Student's Grades", self.view_student_grades),
        ])

    def save_grade(self, student, subject):
        score = valid_score(self.required("Grade (0-100)"))
        self.storage.upsert("grades", {
            "student_id": student["student_id"],
            "subject_id": subject["subject_id"],
            "score": str(score),
        })
        print("Grade saved.")

    def add_grade(self):
        student = self.select("students")
        subject = self.select("subjects")
        self.save_grade(student, subject)

    def add_multiple_grades(self):
        subject = self.select("subjects")
        print("Enter students for this subject. Leave Student ID blank to finish.")
        while True:
            student_id = input("Student ID: ").strip()
            if not student_id:
                return
            student = self.storage.find("students", student_id)
            if student is None:
                print(f"Student ID '{student_id}' does not exist.")
                continue
            try:
                self.save_grade(student, subject)
            except ValueError as error:
                print(f"Error: {error}")

    def view_grades(self, student_id=None):
        rows = []
        for grade in self.storage.rows("grades"):
            if student_id is not None and grade["student_id"] != student_id:
                continue
            student = self.storage.find("students", grade["student_id"])
            subject = self.storage.find("subjects", grade["subject_id"])
            rows.append([grade["student_id"], f"{student['first_name']} {student['last_name']}",
                         grade["subject_id"], subject["name"], grade["score"]])
        self.display(["Student ID", "Student", "Subject ID", "Subject", "Grade"], rows)

    def view_student_grades(self):
        student = self.select("students")
        self.view_grades(student["student_id"])

    def attendance_menu(self):
        self.menu("Attendance", [
            ("Record / Update Student Attendance", self.record_attendance),
            ("View All Attendance Records", self.view_attendance),
            ("View a Student's Attendance", self.view_student_attendance),
        ])

    def record_attendance(self):
        student = self.select("students")
        today = date.today().isoformat()
        attendance_date = valid_date(input(f"Date YYYY-MM-DD [{today}]: ").strip() or today)
        for number, status in enumerate(ATTENDANCE_STATUSES, start=1):
            print(f"{number}: {status}")
        choice = self.required("Status (number or name)")
        statuses = {str(i): status for i, status in enumerate(ATTENDANCE_STATUSES, start=1)}
        statuses.update({status.lower(): status for status in ATTENDANCE_STATUSES})
        status = statuses.get(choice.lower())
        if status is None:
            raise ValueError("Choose Present, Absent, Late, or Excused (1-4).")
        self.storage.upsert("attendance", {
            "student_id": student["student_id"], "date": attendance_date, "status": status,
        })
        print("Attendance saved.")

    def view_attendance(self, student_id=None):
        rows = []
        records = sorted(self.storage.rows("attendance"),
                         key=lambda row: (row["date"], row["student_id"]))
        for record in records:
            if student_id is not None and record["student_id"] != student_id:
                continue
            student = self.storage.find("students", record["student_id"])
            rows.append([record["student_id"], f"{student['first_name']} {student['last_name']}",
                         record["date"], record["status"]])
        self.display(["Student ID", "Student", "Date", "Status"], rows)

    def view_student_attendance(self):
        student = self.select("students")
        self.view_attendance(student["student_id"])

    def reports_menu(self):
        self.menu("Basic Report", [
            ("Count Registered Students", lambda: self.count_records("students")),
            ("Count Registered Teachers", lambda: self.count_records("teachers")),
            ("School Summary", self.school_summary),
        ])

    def count_records(self, table):
        print(f"Total {table}: {len(self.storage.rows(table))}")

    def school_summary(self):
        for table in ("students", "teachers", "classes", "subjects"):
            self.count_records(table)
        students = self.storage.rows("students")
        class_rows = [
            [school_class["class_id"], school_class["name"],
             sum(student["class_id"] == school_class["class_id"] for student in students)]
            for school_class in self.storage.rows("classes")
        ]
        print("\nStudents per class:")
        self.display(["Class ID", "Class", "Students"], class_rows)
        print(f"Unassigned students: {sum(not row['class_id'] for row in students)}")
        grades = self.storage.rows("grades")
        if grades:
            average = sum(float(row["score"]) for row in grades) / len(grades)
            print(f"Overall grade average: {average:.2f} ({len(grades)} grades)")
        else:
            print("No grades recorded.")
        attendance = self.storage.rows("attendance")
        print(f"Attendance records: {len(attendance)}")
        for status in ATTENDANCE_STATUSES:
            print(f"  {status}: {sum(row['status'] == status for row in attendance)}")


def main():
    try:
        storage = CSVStorage()
        SchoolManagement(storage).run()
    except (EOFError, KeyboardInterrupt):
        print("\nGoodbye. Completed changes have already been saved.")
        return 0
    except (OSError, ValueError, UnicodeError) as error:
        print(f"Could not load CSV records: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
