from database import SessionLocal
from models.historical import HistoricalIncident
db = SessionLocal()
db.query(HistoricalIncident).delete()
db.commit()
print('Cleared all historical incidents')
db.close()