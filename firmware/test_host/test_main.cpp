#include "harness.h"

int main() {
  int failed_tests = 0;
  for (const harness::Test& t : harness::registry()) {
    const int before = harness::failures();
    t.fn();
    const bool ok = harness::failures() == before;
    failed_tests += ok ? 0 : 1;
    std::printf("[%s] %s\n", ok ? " OK " : "FAIL", t.name);
  }
  std::printf("\n%zu tests, %d checks, %d failed checks, %d failed tests\n", harness::registry().size(),
              harness::checks(), harness::failures(), failed_tests);
  return failed_tests ? 1 : 0;
}
