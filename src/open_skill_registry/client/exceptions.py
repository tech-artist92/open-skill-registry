class OpenSkillRegistryClientError(Exception):
    pass

class NotFoundError(OpenSkillRegistryClientError):
    pass

class SkillNotFoundError(NotFoundError):
    pass

class AuthenticationError(OpenSkillRegistryClientError):
    pass

class DuplicateVersionError(OpenSkillRegistryClientError):
    pass
