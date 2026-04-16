class RobloxException(Exception):
    ...

class InvalidCookie(RobloxException):
    def __init__(self, message: str = 'Invalid cookie') -> None:
        super().__init__(message)

class AccountBanned(RobloxException):
    def __init__(self, message: str = 'Account banned') -> None:
        super().__init__(message)

class RegisteredEarlier1Week(RobloxException):
    def __init__(self, message: str = 'Account registered earlier 1 week') -> None:
        super().__init__(message)
