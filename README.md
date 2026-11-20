# info301-group1-python-project


# Terminal School Management

Run the program with Python 3.10 or newer:

```console
python main.py
```

Use the numbered menus to manage students and teachers, create classes and
subjects, assign students to classes and teachers to subjects, record grades and
attendance, and view reports. Each submenu includes a return option.

Every successful change is saved immediately. The program creates these UTF-8
CSV files in `data/` beside `main.py` and reloads them when you next run it:

| File | Records |
| --- | --- |
| `students.csv` | Student ID, first name, last name, assigned class ID |
| `teachers.csv` | Teacher ID, first name, last name |
| `classes.csv` | Class ID, class name |
| `subjects.csv` | Subject ID, subject name, assigned teacher ID |
| `grades.csv` | Student ID, subject ID, score |
| `attendance.csv` | Student ID, date, status |

IDs are required, unique within each record type, and case-sensitive. Create a
student, teacher, class, or subject before using its ID in an assignment. A
student can have one assigned class; a subject can have one assigned teacher.
Repeating an assignment changes the existing assignment.

Grades range from 0 to 100. There is one current grade per student and subject;
entering another grade for that pair updates it. For multiple students' grades,
choose a subject and enter each student's ID and grade, then leave the next
Student ID blank to finish. Each grade is saved as it is entered.

Attendance has one record per student per date (`YYYY-MM-DD`). Press Enter at
the date prompt to use today. Statuses are Present, Absent, Late, and Excused.
Recording attendance again for the same student and date updates the status.

When updating names, leave a field blank to keep it. Deleting a student also
deletes that student's grades and attendance after confirmation. Deleting a
teacher clears their subject assignments while keeping the subjects.

CSV fields containing commas, quotes, or Unicode characters are supported.
Keep the header rows when editing files, and close the program before making
manual CSV edits. Invalid existing data is reported at startup without
overwriting it. Back up the `data/` folder to preserve your records.

Run the automated checks with:

```console
python -m unittest discover -s tests -v
```
