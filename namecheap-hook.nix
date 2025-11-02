{
  writers,
  playwright-driver,
}:
let
  name = "namecheap-hook";
in
writers.writePython3Bin "${name}" {
  libraries = (
    python-pkgs: with python-pkgs; [
      requests
      playwright
      pyotp
    ]
  );

  makeWrapperArgs = [
    "--set PLAYWRIGHT_BROWSERS_PATH ${playwright-driver.browsers}"
    "--set PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS true"
  ];
} (builtins.readFile ./${name}.py)
