// Minimal self-registering test harness (C++17, no dependencies).
#pragma once

#include <cmath>
#include <cstdio>
#include <functional>
#include <vector>

namespace harness {

struct Test {
  const char* name;
  std::function<void()> fn;
};
inline std::vector<Test>& registry() {
  static std::vector<Test> r;
  return r;
}
inline int& failures() {
  static int f = 0;
  return f;
}
inline int& checks() {
  static int c = 0;
  return c;
}
struct Registrar {
  Registrar(const char* n, std::function<void()> f) { registry().push_back({n, std::move(f)}); }
};

}  // namespace harness

#define HT_CAT2(a, b) a##b
#define HT_CAT(a, b) HT_CAT2(a, b)
#define TEST_CASE(name)                                                         \
  static void HT_CAT(test_fn_, __LINE__)();                                     \
  static harness::Registrar HT_CAT(test_reg_, __LINE__)(name, HT_CAT(test_fn_, __LINE__)); \
  static void HT_CAT(test_fn_, __LINE__)()

#define CHECK(cond)                                                     \
  do {                                                                  \
    ++harness::checks();                                                \
    if (!(cond)) {                                                      \
      ++harness::failures();                                            \
      std::printf("  FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);     \
    }                                                                   \
  } while (0)

#define CHECK_NEAR(a, b, tol)                                                                          \
  do {                                                                                                 \
    ++harness::checks();                                                                               \
    const double ht_a = (a), ht_b = (b);                                                               \
    if (!(std::fabs(ht_a - ht_b) <= (tol))) {                                                          \
      ++harness::failures();                                                                           \
      std::printf("  FAIL %s:%d: %s = %.4f, expected %.4f +- %.4f\n", __FILE__, __LINE__, #a, ht_a, ht_b, \
                  static_cast<double>(tol));                                                           \
    }                                                                                                  \
  } while (0)
