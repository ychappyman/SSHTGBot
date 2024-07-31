import os

class LanguageManager:
    def __init__(self):
        self.language = os.getenv('LANGUAGE', 'zh')

    def get_language(self):
        return self.language

    def set_language(self, language):
        self.language = language

language_manager = LanguageManager()
