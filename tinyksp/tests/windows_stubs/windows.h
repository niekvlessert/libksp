#pragma once
using HANDLE = void*;
using DWORD = unsigned long;
#define STD_OUTPUT_HANDLE ((DWORD)-11)
#define ENABLE_VIRTUAL_TERMINAL_PROCESSING 0x0004
#define INVALID_HANDLE_VALUE ((HANDLE)(long long)-1)
inline HANDLE GetStdHandle(DWORD) { return nullptr; }
inline int GetConsoleMode(HANDLE, DWORD*) { return 0; }
inline int SetConsoleMode(HANDLE, DWORD) { return 0; }
