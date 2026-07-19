from pathlib import Path

from odin_mcp.services.validation_service import ValidationService

service = ValidationService(Path("."))

summary = service.run()

print("Validation Success:", summary.success)

for result in summary.results:
    print("-" * 60)
    print(result.command)
    print("Return Code:", result.returncode)
    print("Success:", result.success)
