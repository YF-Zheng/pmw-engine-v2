class PMWValidationError(ValueError):
    pass


class WorldValidationError(PMWValidationError):
    pass


class LawValidationError(PMWValidationError):
    pass


class ReferenceValidationError(PMWValidationError):
    pass
