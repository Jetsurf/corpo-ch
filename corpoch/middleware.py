from django.db import connection
 
#This is a probably poor attempt at getting the DB to reconnect when the DB "goes away"

class RefreshDatabaseConnectionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
 
    def __call__(self, request):
        self.refresh_connection()
        response = self.get_response(request)
        return response
 
    def refresh_connection(self):
        try:
            if not connection.is_usable():
                connection.close()
        except:
            pass