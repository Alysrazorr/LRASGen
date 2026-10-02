
FRAMEWORKS = {
    "jersey": {
        "language": "java",
        "name": "Jersey",
        "suffix": ".java",
        "scan_type": "regex",
        "regex": [
            r'@(Path|GET|POST|PUT|DELETE|HEAD|OPTIONS)\b',
        ],
    },
    "jdk": {
        "language": "java",
        "name": "JDK",
        "suffix": ".java",
        "scan_type": "regex",
        "regex": [
            r'@(Path|GET|POST|PUT|DELETE|HEAD|OPTIONS)\b',
            r'implements\s+\w*HttpHandler\b',
        ],
    },
    "spring-boot": {
        "language": "java",
        "name": "Spring Boot",
        "suffix": ".java",
        "scan_type": "regex",
        "regex": [
            r"@(GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|RequestMapping|Controller|RestController)\([^)]*\)",
            r'@(Path|GET|POST|PUT|DELETE|HEAD|OPTIONS)\([^)]*\)',
        ],
    },
    "spring-boot-kotlin": {
        "language": "kotlin",
        "name": "Spring Boot",
        "suffix": ".kt",
        "scan_type": "regex",
        "regex": [
            r"@(GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|RequestMapping|Controller|RestController)\([^)]*\)"
        ],
    },
    "aspnetcore": {
        "language": "csharp",
        "name": "ASP.NET Core",
        "suffix": ".cs",
        "scan_type": "regex",
        "regex": [
            r"(HttpGet|HttpPost|HttpPut|HttpPatch|HttpDelete)\b"
        ],
    },
    "flask": {
        "language": "python",
        "name": "Flask",
        "suffix": ".py",
        "scan_type": "special",
        "regex": [
            r'@\w*app\.(route|get|post|put|delete|patch)\([\'"][^\'"]+[\'"]\)',
            r'@\w*\.(route|get|post|put|delete|patch)\([\'"][^\'"]+[\'"]\)',
        ],
    },
    "django": {
        "language": "python",
        "name": "Django",
        "suffix": ".py",
        "scan_type": "special",
        "regex": [],
    },
    "webpy": {
        "language": "python",
        "name": "Web.py",
        "suffix": ".py",
        "scan_type": "special",
        "regex": [],
    },
    "tornado": {
        "language": "python",
        "name": "Tornado",
        "suffix": ".py",
        "scan_type": "special",
        "regex": [],
    },
    "express": {
        "language": "javascript",
        "name": "Express",
        "suffix": ".js",
        "scan_type": "regex",
        "regex": [
            r'(?:app|router)\.(get|post|put|delete|patch|all)\(',
        ],
    },
    "koa": {
        "language": "typescript",
        "name": "Koa",
        "suffix": ".ts",
        "scan_type": "regex",
        "regex": [
            r'(?:app|router)\.(get|post|put|delete|patch|all)\(',
        ],
    },
    "nextjs": {
        "language": "javascript",
        "name": "Next.js",
        "suffix": ".js",
        "scan_type": "special",
        "regex": [],
    },
    "nestjs": {
        "language": "typescript",
        "name": "NestJS",
        "suffix": ".ts",
        "scan_type": "regex",
        "regex": [
            r'@(Controller|Get|Post|Put|Delete|Patch|Options|Head|All)\([^)]*\)',
        ],
    },
}
