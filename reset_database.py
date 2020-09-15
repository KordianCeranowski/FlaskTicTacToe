from app import db
import os

os.remove("database.db")
print('database removed')
db.create_all()
print('new database created')
