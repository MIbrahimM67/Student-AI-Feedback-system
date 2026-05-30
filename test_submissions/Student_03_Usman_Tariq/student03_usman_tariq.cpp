// Student: Usman Tariq | Level: GOOD (7.5/10)
// Correct logic but uses printf/scanf mix instead of consistent cout/cin
// Also missing return type hint, minor style issues

#include <iostream>
#include <cstdio>
using namespace std;

int main() {
    int x, y;
    printf("Enter two numbers: ");
    scanf("%d %d", &x, &y);
    int result = x + y;
    cout << "Sum = " << result << endl;
    return 0;
}
