#pragma once
#include <cstdio>
int _isatty(int);
int _fileno(std::FILE*);
int _setmode(int, int);
std::FILE* _popen(const char*, const char*);
int _pclose(std::FILE*);
