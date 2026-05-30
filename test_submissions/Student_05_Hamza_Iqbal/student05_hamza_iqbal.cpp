// Student: Hamza Iqbal | Level: PARTIAL (4/10)
// Uses a function which is good initiative, but function logic has a bug:
// it multiplies instead of adds. Shows some structural understanding.

#include <iostream>
using namespace std;

int addNumbers(int a, int b) {
    return a * b;  // BUG: should be a + b
}

int main() {
    int num1, num2;
    cout << "First number: ";
    cin >> num1;
    cout << "Second number: ";
    cin >> num2;
    
    cout << "Result: " << addNumbers(num1, num2) << endl;
    return 0;
}
