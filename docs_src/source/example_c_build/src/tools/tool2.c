#include <stdio.h>

#include "a1.h"
#include "a2.h"
#include "a3.h"
#include "b1.h"
#include "b2.h"
#include "b3.h"


int main() {
    printf("%s\n", __FILE__);
    a1();
    a2();
    a3();
    b1();
    b2();
    b3();
}
